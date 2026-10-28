"""Whole-image AI-generation (diffusion/GAN) classifier."""
from __future__ import annotations

import numpy as np
from PIL import Image

from ..utils import clamp01, deep_enabled, resize_max
from .models import get_model

INPUT_MAX_SIDE = 768   # the processor resizes to the model's input size anyway; keep transfer small


def _unavailable(expl: str, details: dict | None = None) -> dict:
    return {"key": "ai_generated", "label": "AI-generated image detector", "score": 0.0, "available": False,
            "explanation": expl, "details": details or {}}


def analyze_ai_generated(rgb: np.ndarray) -> tuple[dict, np.ndarray | None]:
    """Returns (signal, cam_grid_for_full_view or None)."""
    if not deep_enabled():
        return _unavailable("Deep-learning models are disabled on this server (ML_ENABLE_DEEP=false)."), None
    model = get_model("ai_generated")
    if not model.load():
        return _unavailable("The AI-image model is not available on this server (offline or not downloaded).",
                            {"model": model.id, "error": model.error}), None
    small, _ = resize_max(rgb, INPUT_MAX_SIDE)
    h, w = small.shape[:2]
    views = [Image.fromarray(np.ascontiguousarray(small))]
    # Second view: centre square crop (the processor squashes to a square; a crop keeps aspect ratio).
    if abs(h - w) > 0.15 * max(h, w):
        s = min(h, w)
        y0, x0 = (h - s) // 2, (w - s) // 2
        views.append(Image.fromarray(np.ascontiguousarray(small[y0:y0 + s, x0:x0 + s])))
    try:
        probs, cams = model.predict(views)
    except Exception as exc:
        return _unavailable(f"The AI-image model failed on this image ({type(exc).__name__})."), None
    p = clamp01(float(np.mean(probs)))
    if p >= 0.8:
        expl = (f"The AI-image detector finds strong signs that the whole picture was produced by an image "
                f"generator such as a diffusion model or GAN ({p * 100:.0f}% probability).")
    elif p >= 0.5:
        expl = f"The AI-image detector leans towards AI generation ({p * 100:.0f}% probability), but not decisively."
    else:
        expl = f"The AI-image detector considers this a camera/real image ({(1 - p) * 100:.0f}% probability real)."
    return {
        "key": "ai_generated", "label": "AI-generated image detector", "score": p, "available": True,
        "explanation": expl,
        "details": {"model": model.id, "views": len(views), "per_view": [round(x, 4) for x in probs]},
    }, cams[0]
