"""Noise-residual inconsistency.

Every camera leaves a fairly uniform sensor-noise "grain" that depends mainly on brightness. Spliced
content from another photo, AI in-painting, cloning/healing brushes and blurring all change the local
noise level. We estimate per-block noise from a median-filter residual (robust MAD estimate), model
the expected level from brightness and texture, and flag coherent clusters that deviate strongly.
"""
from __future__ import annotations

import cv2
import numpy as np

from ..preprocessing import LoadedImage
from ..utils import block_reduce, clamp01, clusters_from_grid, resize_max, robust_residual_z

NOISE_MAX_SIDE = 2048
NOISE_TARGET_BLOCKS = 64
NOISE_Z_THRESHOLD = 3.5
NOISE_MIN_BLOCKS = 8
NOISE_MIN_AREA_FRAC = 0.003
NOISE_MAX_AREA_FRAC = 0.40
NOISE_EVIDENCE_MID = 6.5
NOISE_EVIDENCE_SCALE = 1.6
NOISE_MIN_Z_SCALE = 0.12           # log-sigma units
FLAT_PIXEL_FRACTION = 0.3
HIGH_TEXTURE_PERCENTILE = 80
LOW_NOISE_SIGMA = 0.35


def analyze_noise(img: LoadedImage) -> dict:
    gray, s = resize_max(img.gray, NOISE_MAX_SIDE)
    H, W = gray.shape
    scale_to_orig = img.width / float(W)
    B = int(max(8, round(max(H, W) / NOISE_TARGET_BLOCKS)))

    g8 = np.clip(gray, 0, 255).astype(np.uint8)
    med = cv2.medianBlur(g8, 3).astype(np.float32)
    resid = gray - med
    absr = np.abs(resid)
    gx = cv2.Sobel(med, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(med, cv2.CV_32F, 0, 1, ksize=3)
    grad = cv2.magnitude(gx, gy)
    # Per-block noise sigma estimated only on the flattest pixels of the block, so that texture and
    # edges (which also leak into the residual) influence the estimate as little as possible.
    nby, nbx = H // B, W // B
    G = grad[: nby * B, : nbx * B].reshape(nby, B, nbx, B).transpose(0, 2, 1, 3).reshape(nby * nbx, B * B)
    R = absr[: nby * B, : nbx * B].reshape(nby, B, nbx, B).transpose(0, 2, 1, 3).reshape(nby * nbx, B * B)
    k = max(4, int(FLAT_PIXEL_FRACTION * B * B))
    idx = np.argpartition(G, k, axis=1)[:, :k]
    sig_b = (np.median(np.take_along_axis(R, idx, axis=1), axis=1) * 1.4826
             + np.mean(np.take_along_axis(R, idx, axis=1), axis=1) * 0.25).reshape(nby, nbx).astype(np.float32)
    br_b = block_reduce(gray, B, "mean")
    tex_b = block_reduce(grad, B, "mean")

    valid = (br_b > 12) & (br_b < 243)
    ly = np.log(sig_b + 0.05)
    b = br_b / 255.0
    lt = np.log1p(tex_b)
    z = robust_residual_z(ly, [b, b * b, lt, lt * lt], valid, min_scale=NOISE_MIN_Z_SCALE).reshape(sig_b.shape).astype(np.float32)
    zs = cv2.GaussianBlur(z, (3, 3), 0.8)
    # "Noisier than expected" in the most textured blocks is usually fine texture leaking into the
    # residual (foliage, hair, fabric), not a different noise source: ignore those positive outliers.
    tex_cut = np.percentile(tex_b[valid], HIGH_TEXTURE_PERCENTILE) if valid.any() else np.inf
    zs = np.where((zs > 0) & (tex_b > tex_cut), 0.0, zs).astype(np.float32)
    az = np.abs(zs)

    mask = (az > NOISE_Z_THRESHOLD) & valid
    mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)).astype(bool)
    clusters = clusters_from_grid(az, mask, B, scale_to_orig, img.width, img.height,
                                  NOISE_MIN_BLOCKS, NOISE_MIN_AREA_FRAC)
    clusters = [c for c in clusters if c["area_frac"] <= NOISE_MAX_AREA_FRAC]

    evidence = 0.0
    for c in clusters[:3]:
        ev = (c["mean_score"] - NOISE_Z_THRESHOLD + 1.0) * (1.0 + np.log1p(c["n_blocks"] / NOISE_MIN_BLOCKS))
        evidence = max(evidence, float(ev))
    raw = 1.0 / (1.0 + np.exp(-(evidence - NOISE_EVIDENCE_MID) / NOISE_EVIDENCE_SCALE)) if evidence > 0 else 0.0
    frac_anom = float(mask[valid].mean()) if valid.any() else 0.0

    # Global noise level (useful context: very low noise = heavy denoise / smoothing / synthetic image)
    global_sigma = float(np.median(sig_b[valid])) if valid.any() else float(np.median(sig_b))
    reliability = 1.0
    if img.jpeg_quality is not None and img.jpeg_quality < 70:
        reliability *= 0.75
    if min(img.width, img.height) < 300:
        reliability *= 0.7
    if global_sigma < LOW_NOISE_SIGMA:
        # Practically noise-free (rendered / AI-generated / heavily denoised): block-to-block noise
        # comparisons are dominated by quantisation and become unreliable.
        reliability *= 0.4
    score = clamp01(max(raw * reliability, 0.03 + 0.5 * frac_anom * reliability))

    regions = [{"box": c["box"],
                "score": clamp01(1.0 / (1.0 + np.exp(-(c["mean_score"] - 4.5))) * reliability),
                "source": "noise"} for c in clusters]

    if score >= 0.6:
        expl = ("The camera-noise pattern is inconsistent: some areas are much noisier or smoother than the rest "
                "of the image, which happens when content from another source is inserted or retouched.")
    elif score >= 0.35:
        expl = ("Some areas have a noticeably different noise level than the rest of the image; this may be "
                "editing, but also focus blur, denoising or strong compression.")
    else:
        expl = "The sensor-noise pattern is consistent across the image."
    if global_sigma < LOW_NOISE_SIGMA:
        expl += " The image is unusually noise-free overall (heavy smoothing, rendering or AI generation can cause this)."

    return {
        "key": "noise",
        "label": "Noise residual consistency",
        "score": float(score),
        "available": True,
        "explanation": expl,
        "details": {
            "block_size_px": int(round(B * scale_to_orig)),
            "anomalous_block_fraction": round(frac_anom, 4),
            "clusters": len(clusters),
            "evidence": round(evidence, 3),
            "global_noise_sigma": round(global_sigma, 3),
            "reliability": round(reliability, 2),
        },
        "_regions": regions,
        "_zmap": np.where(valid, az, 0).astype(np.float32),
        "_block": B,
        "_map_shape": (H, W),
    }
