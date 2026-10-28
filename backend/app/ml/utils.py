"""Small numeric helpers shared by the ML modules (pure numpy / OpenCV)."""
from __future__ import annotations

import math
import os
from typing import Any

import cv2
import numpy as np


def env_flag(name: str, default: bool = True) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() not in ("0", "false", "no", "off", "")


def deep_enabled() -> bool:
    return env_flag("ML_ENABLE_DEEP", True)


def model_cache_dir() -> str:
    path = os.path.abspath(os.environ.get("MODEL_CACHE_DIR", "./models_cache"))
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path


def clamp01(x: float) -> float:
    if x is None or not math.isfinite(float(x)):
        return 0.0
    return float(min(1.0, max(0.0, float(x))))


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-float(x)))


def to_py(obj: Any) -> Any:
    """Recursively convert numpy scalars/arrays (and tuples) into plain JSON-friendly Python types."""
    if isinstance(obj, dict):
        return {str(k): to_py(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_py(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return to_py(obj.tolist())
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return f if math.isfinite(f) else None
    if isinstance(obj, bytes):
        return obj.decode("utf-8", "replace")
    return obj


def resize_max(arr: np.ndarray, max_side: int, interpolation: int = cv2.INTER_AREA) -> tuple[np.ndarray, float]:
    """Downscale so that max(h, w) <= max_side. Returns (array, scale) with scale = new/original."""
    h, w = arr.shape[:2]
    m = max(h, w)
    if m <= max_side:
        return arr, 1.0
    s = max_side / float(m)
    out = cv2.resize(arr, (max(1, int(round(w * s))), max(1, int(round(h * s)))), interpolation=interpolation)
    return out, s


def block_reduce(arr: np.ndarray, block: int, func: str = "mean") -> np.ndarray:
    """Reduce a 2-D array over non-overlapping block x block tiles (edge remainder is cropped)."""
    h, w = arr.shape[:2]
    nby, nbx = h // block, w // block
    if nby == 0 or nbx == 0:
        return np.zeros((max(nby, 1), max(nbx, 1)), dtype=np.float32)
    a = arr[: nby * block, : nbx * block].reshape(nby, block, nbx, block)
    if func == "mean":
        return a.mean(axis=(1, 3)).astype(np.float32)
    if func == "median":
        return np.median(a.transpose(0, 2, 1, 3).reshape(nby, nbx, -1), axis=2).astype(np.float32)
    if func == "max":
        return a.max(axis=(1, 3)).astype(np.float32)
    raise ValueError(func)


def robust_residual_z(y: np.ndarray, X: np.ndarray, valid: np.ndarray, iters: int = 3,
                      min_scale: float = 0.0) -> np.ndarray:
    """Robustly regress y on X (columns, intercept added) over `valid` samples and return
    robust z-scores of the residuals (MAD-scaled). Invalid samples get z = 0."""
    y = y.astype(np.float64).ravel()
    valid = valid.ravel().astype(bool)
    n = y.size
    A = np.column_stack([np.ones(n)] + [x.astype(np.float64).ravel() for x in X])
    use = valid.copy()
    if use.sum() < A.shape[1] + 5:
        return np.zeros_like(y).reshape(-1)
    coef = None
    for _ in range(iters):
        coef, *_ = np.linalg.lstsq(A[use], y[use], rcond=None)
        r = y - A @ coef
        med = np.median(r[use])
        mad = np.median(np.abs(r[use] - med)) + 1e-9
        use = valid & (np.abs(r - med) < 3.0 * 1.4826 * mad)
        if use.sum() < A.shape[1] + 5:
            use = valid
            break
    r = y - A @ coef
    med = np.median(r[valid])
    mad = np.median(np.abs(r[valid] - med))
    # MAD collapses when most residuals are identical (quantised errors, flat images): use a floor
    # based on the trimmed std and an absolute minimum so tiny deviations don't become huge z-scores.
    r_valid = r[valid] - med
    lo, hi = np.percentile(r_valid, [5, 95])
    trimmed_std = float(np.std(r_valid[(r_valid >= lo) & (r_valid <= hi)])) if r_valid.size > 10 else 0.0
    scale = max(1.4826 * mad, 0.7 * trimmed_std, min_scale, 1e-6)
    z = (r - med) / scale
    z[~valid] = 0.0
    return z


def clusters_from_grid(score_grid: np.ndarray, mask: np.ndarray, block: int, scale_to_orig: float,
                       orig_w: int, orig_h: int, min_blocks: int, min_area_frac: float,
                       max_regions: int = 5) -> list[dict]:
    """Connected components of a boolean block grid -> boxes in ORIGINAL image pixels.

    `block` is the block size in analysis pixels; `scale_to_orig` multiplies analysis px -> original px.
    Each cluster dict has box [x, y, w, h], n_blocks, area_frac, mean_score, max_score."""
    m = mask.astype(np.uint8)
    if m.sum() == 0:
        return []
    n, labels, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    total = float(mask.size)
    out = []
    for i in range(1, n):
        cnt = int(stats[i, cv2.CC_STAT_AREA])
        frac = cnt / total
        if cnt < min_blocks or frac < min_area_frac:
            continue
        sel = labels == i
        vals = score_grid[sel]
        x, y, w, h = (int(stats[i, cv2.CC_STAT_LEFT]), int(stats[i, cv2.CC_STAT_TOP]),
                      int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT]))
        k = block * scale_to_orig
        bx, by = int(round(x * k)), int(round(y * k))
        bw, bh = int(round(w * k)), int(round(h * k))
        bx, by = max(0, min(bx, orig_w - 1)), max(0, min(by, orig_h - 1))
        bw, bh = max(1, min(bw, orig_w - bx)), max(1, min(bh, orig_h - by))
        out.append({
            "box": [bx, by, bw, bh],
            "n_blocks": cnt,
            "area_frac": frac,
            "mean_score": float(np.mean(vals)),
            "max_score": float(np.max(vals)),
            "strength": float(np.sum(np.clip(vals, 0, None))),
        })
    out.sort(key=lambda c: c["strength"], reverse=True)
    return out[:max_regions]


def clip_box(box: list[float], w: int, h: int) -> list[int]:
    x, y, bw, bh = [int(round(v)) for v in box]
    x = max(0, min(x, w - 1))
    y = max(0, min(y, h - 1))
    bw = max(1, min(bw, w - x))
    bh = max(1, min(bh, h - y))
    return [x, y, bw, bh]


def iou(a: list[int], b: list[int]) -> float:
    ax2, ay2 = a[0] + a[2], a[1] + a[3]
    bx2, by2 = b[0] + b[2], b[1] + b[3]
    iw = max(0, min(ax2, bx2) - max(a[0], b[0]))
    ih = max(0, min(ay2, by2) - max(a[1], b[1]))
    inter = iw * ih
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0
