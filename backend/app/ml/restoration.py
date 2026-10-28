"""Content restoration (in-painting) of suspicious / user-selected regions.

Baseline: OpenCV Telea in-painting on a slightly dilated mask. A heavier learned in-painter (LaMa)
was deliberately not bundled: it adds ~200 MB and is slow/fragile on CPU. Every output carries a
visible "AI-RECONSTRUCTED" stamp and the restored area is outlined, so it can never be mistaken
for original evidence.
"""
from __future__ import annotations

import os

import cv2
import numpy as np
from PIL import Image

from .preprocessing import oriented_pil

MASK_DILATE_PX_FRAC = 0.006     # dilation radius relative to the longer image side
MASK_DILATE_MIN_PX = 3
INPAINT_RADIUS_FRAC = 0.004
INPAINT_MAX_SIDE = 2048         # in-paint at most at this size (Telea is O(mask area))
MAX_MASK_FRACTION = 0.6         # refuse to "restore" (hallucinate) more than this share of the image
NOTE = "AI-reconstructed region — not original evidence"
LABEL_TEXT = "AI-RECONSTRUCTED"


def build_mask(width: int, height: int, boxes: list[list[int]] | None, mask_path: str | None) -> np.ndarray:
    mask = np.zeros((height, width), np.uint8)
    if boxes:
        for b in boxes:
            if b is None or len(b) < 4:
                continue
            x, y, w, h = [int(round(float(v))) for v in b[:4]]
            x0, y0 = max(0, x), max(0, y)
            x1, y1 = min(width, x + max(0, w)), min(height, y + max(0, h))
            if x1 > x0 and y1 > y0:
                mask[y0:y1, x0:x1] = 255
    if mask_path and os.path.isfile(mask_path):
        with Image.open(mask_path) as m:
            if m.mode in ("RGBA", "LA"):
                # drawn masks from a canvas: use alpha *and* brightness
                a = np.asarray(m.convert("RGBA"), np.uint8)
                mm = ((a[..., 3] > 127) & (a[..., :3].max(axis=2) > 127)).astype(np.uint8) * 255
            else:
                mm = (np.asarray(m.convert("L"), np.uint8) > 127).astype(np.uint8) * 255
        if mm.shape != (height, width):
            mm = cv2.resize(mm, (width, height), interpolation=cv2.INTER_NEAREST)
        mask = np.maximum(mask, mm)
    return mask


def stamp_label(rgb: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    out = np.ascontiguousarray(rgb.copy())
    h, w = out.shape[:2]
    if mask is not None and mask.any():
        contours, _ = cv2.findContours((mask > 0).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(out, contours, -1, (255, 0, 255), max(1, int(round(max(w, h) / 800))), cv2.LINE_AA)
    font = cv2.FONT_HERSHEY_DUPLEX
    scale = max(0.5, min(w, h) / 900.0)
    th = max(1, int(round(scale * 2)))
    (tw, tht), base = cv2.getTextSize(LABEL_TEXT, font, scale, th)
    pad = max(4, int(6 * scale))
    x0, y0 = pad, pad
    x1, y1 = min(w - 1, x0 + tw + 2 * pad), min(h - 1, y0 + tht + base + 2 * pad)
    overlay = out.copy()
    cv2.rectangle(overlay, (x0, y0), (x1, y1), (0, 0, 0), -1)
    out = cv2.addWeighted(overlay, 0.65, out, 0.35, 0)
    cv2.putText(out, LABEL_TEXT, (x0 + pad, y0 + pad + tht), font, scale, (255, 40, 40), th, cv2.LINE_AA)
    return out


def inpaint(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    h, w = rgb.shape[:2]
    r = max(MASK_DILATE_MIN_PX, int(round(max(h, w) * MASK_DILATE_PX_FRAC)))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    m = cv2.dilate((mask > 0).astype(np.uint8) * 255, k)
    s = min(1.0, INPAINT_MAX_SIDE / float(max(h, w)))
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    if s < 1.0:
        small = cv2.resize(bgr, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        ms = cv2.resize(m, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST)
        rad = max(3, int(round(max(small.shape[:2]) * INPAINT_RADIUS_FRAC)))
        filled_small = cv2.inpaint(small, ms, rad, cv2.INPAINT_TELEA)
        filled = cv2.resize(filled_small, (w, h), interpolation=cv2.INTER_CUBIC)
        # keep original pixels outside the mask at full resolution
        sel = m > 0
        out = bgr.copy()
        out[sel] = filled[sel]
    else:
        rad = max(3, int(round(max(h, w) * INPAINT_RADIUS_FRAC)))
        out = cv2.inpaint(bgr, m, rad, cv2.INPAINT_TELEA)
    return cv2.cvtColor(out, cv2.COLOR_BGR2RGB), m


def fallback_box(width: int, height: int, sus_map: np.ndarray | None) -> list[int]:
    """Box (~10% of the image side) around the hottest point of the suspicion map, or the centre."""
    bw, bh = max(8, width // 10), max(8, height // 10)
    if sus_map is not None and sus_map.size and float(sus_map.max()) > 0:
        yy, xx = np.unravel_index(int(np.argmax(sus_map)), sus_map.shape)
        cx, cy = xx * width / sus_map.shape[1], yy * height / sus_map.shape[0]
    else:
        cx, cy = width / 2, height / 2
    return [int(max(0, cx - bw / 2)), int(max(0, cy - bh / 2)), bw, bh]


def restore(image_path: str, output_path: str, boxes, mask_path, auto_regions_fn) -> dict:
    """auto_regions_fn(image_path) -> (regions, sus_map) used when neither boxes nor mask are given."""
    pil = oriented_pil(image_path)
    rgb = np.asarray(pil, np.uint8)
    h, w = rgb.shape[:2]
    mask = build_mask(w, h, boxes, mask_path)
    source = "user"
    if not mask.any():
        source = "auto"
        regions, sus_map = auto_regions_fn(image_path)
        # Prefer local forensic regions; whole-face / whole-image boxes in-paint badly.
        local = [r for r in regions if r["source"] in ("ela", "noise") and r["score"] >= 0.3]
        chosen = (local or [r for r in regions if r["source"] != "gradcam"] or regions)[:3]
        auto_boxes = [r["box"] for r in chosen] or [fallback_box(w, h, sus_map)]
        mask = build_mask(w, h, auto_boxes, None)
    frac = float((mask > 0).mean())
    method = "opencv_telea"
    note = NOTE
    if frac > MAX_MASK_FRACTION:
        # Too large to reconstruct credibly: keep the image, only label it.
        out = stamp_label(rgb, mask)
        method = "none_mask_too_large"
        note = NOTE + f" (mask covered {frac * 100:.0f}% of the image, so nothing was in-painted)"
    else:
        filled, dil = inpaint(rgb, mask)
        out = stamp_label(filled, dil)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    Image.fromarray(out).save(output_path, "PNG")
    return {"restored_path": os.path.abspath(output_path), "method": method, "note": note,
            "mask_source": source, "mask_fraction": round(frac, 4)}
