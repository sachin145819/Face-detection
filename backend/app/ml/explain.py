"""Explainability: combined suspicion heatmap, CAM-derived regions and the rendered heatmap.png."""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from .utils import clip_box, iou, resize_max

MAP_MAX_SIDE = 1024          # internal resolution of the combined suspicion map
HEATMAP_MAX_SIDE = 1600      # output heatmap.png size (aspect preserved; coords stay in original px)
FACE_CAM_MIN_PROB = 0.5      # show the face CAM only when the face is at least borderline
AI_CAM_MIN_PROB = 0.5
CAM_REGION_THRESHOLD = 0.6   # fraction of CAM max used to outline the "gradcam" region
DEEPFAKE_REGION_MIN_PROB = 0.5
MAX_REGIONS = 8
REGION_MIN_SCORE = 0.25     # weaker candidate regions are dropped from the output

COLOR_REGION = (255, 140, 0)
COLOR_FACE_FAKE = (230, 30, 30)
COLOR_FACE_UNSURE = (255, 190, 0)
COLOR_FACE_REAL = (40, 200, 80)
COLOR_FACE_NA = (170, 170, 170)


def _grid_to_map(grid: np.ndarray, block: int, analysis_shape: tuple[int, int],
                 map_shape: tuple[int, int]) -> np.ndarray:
    H, W = analysis_shape
    mh, mw = map_shape
    nby, nbx = grid.shape
    out = np.zeros((mh, mw), np.float32)
    th = max(1, min(mh, int(round(nby * block * mh / H))))
    tw = max(1, min(mw, int(round(nbx * block * mw / W))))
    out[:th, :tw] = cv2.resize(grid.astype(np.float32), (tw, th), interpolation=cv2.INTER_LINEAR)
    return out


def _norm_cam(cam: np.ndarray) -> np.ndarray | None:
    if cam is None:
        return None
    # Contrast-normalise: only tokens that push towards "fake" clearly more than the typical token
    # light up (the model's evidence is usually spread over the whole image for AI images).
    c = cam.astype(np.float32)
    lo = max(float(np.percentile(c, 50)), 0.0)
    hi = float(c.max())
    if hi - lo <= 1e-6:
        return None
    return np.clip((c - lo) / (hi - lo), 0, 1)


def build_suspicion_map(img_w: int, img_h: int, ela: dict | None, noise: dict | None,
                        faces: list[dict], ai_score: float | None, ai_cam: np.ndarray | None,
                        scores: dict) -> tuple[np.ndarray, float]:
    """Return (map in [0,1] at map resolution, map_scale = map px / original px)."""
    s = min(1.0, MAP_MAX_SIDE / float(max(img_w, img_h)))
    mh, mw = max(1, int(round(img_h * s))), max(1, int(round(img_w * s)))
    combined = np.zeros((mh, mw), np.float32)

    if ela and "_zmap" in ela:
        m = _grid_to_map(ela["_zmap"], ela["_block"], ela["_map_shape"], (mh, mw))
        combined = np.maximum(combined, np.clip((m - 2.0) / 4.0, 0, 1) * (0.35 + 0.65 * scores.get("ela", 0)))
    if noise and "_zmap" in noise:
        m = _grid_to_map(noise["_zmap"], noise["_block"], noise["_map_shape"], (mh, mw))
        combined = np.maximum(combined, np.clip((m - 2.5) / 4.0, 0, 1) * (0.35 + 0.65 * scores.get("noise", 0)))
    combined = cv2.GaussianBlur(combined, (0, 0), max(1.0, max(mh, mw) / 200.0))

    for f in faces:
        p = f.get("deepfake_probability")
        cam = _norm_cam(f.get("_cam"))
        if p is None or cam is None or p < FACE_CAM_MIN_PROB:
            continue
        x, y, w, h = f.get("_crop_box", f["box"])
        x0, y0 = int(x * s), int(y * s)
        x1, y1 = min(mw, int((x + w) * s)), min(mh, int((y + h) * s))
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        patch = cv2.resize(cam, (x1 - x0, y1 - y0), interpolation=cv2.INTER_CUBIC)
        patch = np.clip(patch, 0, 1) * float(p)
        combined[y0:y1, x0:x1] = np.maximum(combined[y0:y1, x0:x1], patch)

    if ai_score is not None and ai_score >= AI_CAM_MIN_PROB:
        cam = _norm_cam(ai_cam)
        if cam is not None:
            up = np.clip(cv2.resize(cam, (mw, mh), interpolation=cv2.INTER_CUBIC), 0, 1)
            combined = np.maximum(combined, up * float(ai_score) * 0.75)
    return np.clip(combined, 0, 1), s


def cam_regions(img_w: int, img_h: int, faces: list[dict], ai_score: float | None,
                ai_cam: np.ndarray | None) -> list[dict]:
    regions = []
    for f in faces:
        p = f.get("deepfake_probability")
        if p is not None and p >= DEEPFAKE_REGION_MIN_PROB:
            regions.append({"box": list(f["box"]), "score": float(p), "source": "deepfake"})
    if ai_score is not None and ai_score >= AI_CAM_MIN_PROB:
        cam = _norm_cam(ai_cam)
        if cam is not None:
            up = cv2.resize(cam, (256, max(1, int(256 * img_h / img_w))), interpolation=cv2.INTER_CUBIC)
            mask = (up >= CAM_REGION_THRESHOLD).astype(np.uint8)
            n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
            if n > 1:
                i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
                k = img_w / 256.0
                x, y, w, h = stats[i, :4]
                box = clip_box([x * k, y * k, w * k, h * k], img_w, img_h)
                regions.append({"box": box, "score": float(ai_score) * float(up[labels == i].mean()),
                                "source": "gradcam"})
    return regions


def merge_regions(regions: list[dict], img_w: int, img_h: int) -> list[dict]:
    regions = sorted(regions, key=lambda r: r["score"], reverse=True)
    kept: list[dict] = []
    for r in regions:
        if r["score"] < REGION_MIN_SCORE:
            continue
        box = clip_box(r["box"], img_w, img_h)
        if any(iou(box, k["box"]) > 0.5 and k["source"] == r["source"] for k in kept):
            continue
        kept.append({"box": box, "score": round(float(min(1.0, max(0.0, r["score"]))), 4), "source": r["source"]})
        if len(kept) >= MAX_REGIONS:
            break
    return kept


def _label(img: np.ndarray, text: str, x: int, y: int, color: tuple, scale: float) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    th = max(1, int(round(scale * 2)))
    (tw, tht), base = cv2.getTextSize(text, font, scale, th)
    y = max(tht + base + 2, y)
    cv2.rectangle(img, (x, y - tht - base - 4), (x + tw + 6, y), color, -1)
    cv2.putText(img, text, (x + 3, y - base - 1), font, scale, (0, 0, 0) if sum(color) > 400 else (255, 255, 255),
                th, cv2.LINE_AA)


def render_heatmap(rgb: np.ndarray, sus_map: np.ndarray, regions: list[dict], faces: list[dict],
                   path: str) -> None:
    base, s = resize_max(rgb, HEATMAP_MAX_SIDE)
    h, w = base.shape[:2]
    heat = cv2.resize(sus_map, (w, h), interpolation=cv2.INTER_LINEAR)
    colored = cv2.applyColorMap((heat * 255).astype(np.uint8), cv2.COLORMAP_JET)
    colored = cv2.cvtColor(colored, cv2.COLOR_BGR2RGB).astype(np.float32)
    alpha = np.clip((heat - 0.08) * 1.1, 0, 0.65)[..., None]
    out = (base.astype(np.float32) * (1 - alpha) + colored * alpha).astype(np.uint8)
    out = np.ascontiguousarray(out)

    lw = max(2, int(round(max(w, h) / 400)))
    fs = max(0.45, max(w, h) / 1600.0 * 0.7)
    for r in regions:
        if r["source"] == "deepfake":
            continue  # drawn with the faces below
        x, y, bw, bh = [int(round(v * s)) for v in r["box"]]
        cv2.rectangle(out, (x, y), (x + bw, y + bh), COLOR_REGION, lw)
        name = {"ela": "ELA", "noise": "Noise", "gradcam": "AI focus"}.get(r["source"], r["source"])
        _label(out, f"{name} {r['score'] * 100:.0f}%", x, y, COLOR_REGION, fs)
    for f in faces:
        p = f.get("deepfake_probability")
        if p is None:
            color, text = COLOR_FACE_NA, "Face"
        else:
            color = COLOR_FACE_FAKE if p >= 0.7 else COLOR_FACE_UNSURE if p >= 0.45 else COLOR_FACE_REAL
            text = f"Face {p * 100:.0f}% fake"
        x, y, bw, bh = [int(round(v * s)) for v in f["box"]]
        cv2.rectangle(out, (x, y), (x + bw, y + bh), color, lw)
        _label(out, text, x, y, color, fs)
    if path.lower().endswith((".jpg", ".jpeg")):   # video frame overlays are saved as JPEG
        Image.fromarray(out).save(path, "JPEG", quality=88)
    else:
        Image.fromarray(out).save(path, "PNG")
