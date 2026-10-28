"""Error Level Analysis (ELA).

The image is re-saved as JPEG at a fixed quality and the per-pixel difference is measured. In an
untouched JPEG every area has gone through the same compression history, so the error level is
explained by local texture (edges re-compress worse than flat areas). Pasted or retouched areas
often have a *different* history, so their error level departs from what their texture predicts.

We therefore regress block error on block texture (robustly) and look for spatially coherent
clusters of blocks with unusually high residual error, instead of thresholding raw ELA (which would
simply highlight edges and give many false positives on normal photos).
"""
from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image

from ..preprocessing import LoadedImage, apply_orientation
from ..utils import block_reduce, clamp01, clusters_from_grid, resize_max, robust_residual_z

ELA_QUALITY = 90
ELA_MAX_PIXELS = 16_000_000        # above this, downscale first (breaks JPEG grid -> lower reliability)
ELA_TARGET_BLOCKS = 96              # ~ number of blocks along the longer side
ELA_Z_THRESHOLD = 3.0               # residual z for a block to count as anomalous
ELA_MIN_BLOCKS = 6
ELA_MIN_AREA_FRAC = 0.002
ELA_MAX_AREA_FRAC = 0.45            # bigger "clusters" are global effects, not local tampering
# Mapping from cluster evidence -> suspicion score.
ELA_EVIDENCE_MID = 5.0              # evidence value giving score 0.5
ELA_EVIDENCE_SCALE = 1.6
LOSSLESS_RELIABILITY = 0.6          # PNG/WebP etc have no JPEG history: ELA evidence is down-weighted
VISUAL_MAX_SIDE = 2048
ELA_MIN_Z_SCALE = 0.08            # log-error units; floor for the residual spread


def _block_size(h: int, w: int) -> int:
    b = max(h, w) / ELA_TARGET_BLOCKS
    return int(max(8, 8 * round(b / 8)))


def compute_ela(img: LoadedImage) -> dict:
    raw = img.raw_rgb
    downscaled = False
    if raw.shape[0] * raw.shape[1] > ELA_MAX_PIXELS:
        s = (ELA_MAX_PIXELS / (raw.shape[0] * raw.shape[1])) ** 0.5
        raw = cv2.resize(raw, (int(raw.shape[1] * s), int(raw.shape[0] * s)), interpolation=cv2.INTER_AREA)
        downscaled = True
    buf = io.BytesIO()
    Image.fromarray(raw).save(buf, "JPEG", quality=ELA_QUALITY)
    buf.seek(0)
    resaved = np.asarray(Image.open(buf).convert("RGB"), dtype=np.int16)
    diff_rgb = np.abs(raw.astype(np.int16) - resaved).astype(np.uint8)
    diff_rgb = np.ascontiguousarray(apply_orientation(diff_rgb, img.orientation))
    return {"diff_rgb": diff_rgb, "downscaled": downscaled}


def save_ela_visual(diff_rgb: np.ndarray, path: str) -> None:
    d = diff_rgb.astype(np.float32)
    hi = float(np.percentile(d, 99.5)) if d.size else 1.0
    gain = 255.0 / max(hi, 4.0)
    vis = np.clip(d * gain, 0, 255).astype(np.uint8)
    vis, _ = resize_max(vis, VISUAL_MAX_SIDE)
    Image.fromarray(vis).save(path, "PNG", optimize=False)


def analyze_ela(img: LoadedImage, ela_png_path: str | None) -> dict:
    res = compute_ela(img)
    diff_rgb = res["diff_rgb"]
    if ela_png_path:
        save_ela_visual(diff_rgb, ela_png_path)

    # Luminance error: chroma subsampling makes colour edges re-compress badly in *every* JPEG, so
    # the colour channels would mostly highlight saturated edges rather than editing.
    err = (0.299 * diff_rgb[..., 0] + 0.587 * diff_rgb[..., 1] + 0.114 * diff_rgb[..., 2]).astype(np.float32)
    H, W = err.shape
    scale_to_orig = img.width / float(W)
    gray = img.gray if (img.gray.shape[0] == H) else cv2.resize(img.gray, (W, H), interpolation=cv2.INTER_AREA)

    B = _block_size(H, W)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    tex = cv2.magnitude(gx, gy)
    e_b = block_reduce(err, B, "mean")
    t_b = block_reduce(tex, B, "mean")
    br_b = block_reduce(gray, B, "mean")
    valid = (br_b > 6) & (br_b < 249)   # clipped highlights/shadows carry no ELA information
    ly = np.log1p(e_b)
    lt = np.log1p(t_b)
    z = robust_residual_z(ly, [lt, lt ** 2], valid, min_scale=ELA_MIN_Z_SCALE).reshape(e_b.shape).astype(np.float32)

    lossless = img.format in ("PNG", "WEBP", "BMP", "TIFF", "GIF")
    reliability = 1.0
    notes = []
    if lossless:
        reliability *= LOSSLESS_RELIABILITY
        notes.append(f"{img.format} files carry no JPEG compression history, so ELA is less informative")
    if res["downscaled"]:
        reliability *= 0.8
        notes.append("very large image was downscaled for ELA")
    if img.jpeg_quality is not None and img.jpeg_quality < 70:
        reliability *= 0.7
        notes.append(f"heavy JPEG compression (estimated quality {img.jpeg_quality:.0f}) masks ELA traces")

    # Anomalous blocks: lightly smooth z to favour coherent areas over isolated noisy blocks.
    zs = cv2.GaussianBlur(z, (3, 3), 0.8)
    mask = (zs > ELA_Z_THRESHOLD) & valid
    mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)).astype(bool)
    clusters = clusters_from_grid(zs, mask, B, scale_to_orig, img.width, img.height,
                                  ELA_MIN_BLOCKS, ELA_MIN_AREA_FRAC)
    clusters = [c for c in clusters if c["area_frac"] <= ELA_MAX_AREA_FRAC]

    evidence = 0.0
    for c in clusters[:3]:
        # strength of the anomaly x (log) size of the area
        ev = (c["mean_score"] - ELA_Z_THRESHOLD + 1.0) * (1.0 + np.log1p(c["n_blocks"] / ELA_MIN_BLOCKS))
        evidence = max(evidence, float(ev))
    raw_score = 1.0 / (1.0 + np.exp(-(evidence - ELA_EVIDENCE_MID) / ELA_EVIDENCE_SCALE)) if evidence > 0 else 0.0
    # Global non-uniformity: share of valid blocks that are anomalous.
    frac_anom = float(mask[valid].mean()) if valid.any() else 0.0
    score = clamp01(max(raw_score * reliability, 0.03 + 0.5 * frac_anom * reliability))

    regions = []
    for c in clusters:
        rs = clamp01(1.0 / (1.0 + np.exp(-(c["mean_score"] - 4.0))) * (0.6 + 0.4 * reliability))
        regions.append({"box": c["box"], "score": rs, "source": "ela"})

    if score >= 0.6:
        expl = (f"Error Level Analysis found {len(clusters)} area(s) whose compression error is much higher "
                "than their texture explains — a typical trace of pasted or retouched content.")
    elif score >= 0.35:
        expl = ("Error Level Analysis shows some areas with unusual compression error; this can be editing, "
                "but also strong local sharpening or re-compression.")
    else:
        expl = "Error Level Analysis shows a consistent compression error across the image (no local anomalies)."
    if notes:
        expl += " Note: " + "; ".join(notes) + "."

    return {
        "key": "ela",
        "label": "Error Level Analysis",
        "score": float(score),
        "available": True,
        "explanation": expl,
        "details": {
            "resave_quality": ELA_QUALITY,
            "block_size_px": int(round(B * scale_to_orig)),
            "anomalous_block_fraction": round(frac_anom, 4),
            "clusters": len(clusters),
            "evidence": round(evidence, 3),
            "reliability": round(reliability, 2),
            "mean_error": round(float(err.mean()), 3),
            "jpeg_quality_estimate": img.jpeg_quality,
        },
        "_regions": regions,
        "_zmap": np.where(valid, zs, 0).astype(np.float32),
        "_block": B,
        "_map_shape": (H, W),
    }
