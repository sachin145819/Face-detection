"""Fixtures for the ML pipeline tests: synthetic photo-like images (no network needed)."""
from __future__ import annotations

import io
import os
import sys

import numpy as np
import pytest
from PIL import Image

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


def _photo_like(w: int = 900, h: int = 640, seed: int = 0) -> np.ndarray:
    """Smooth gradients + soft shapes + texture + sensor-like noise, then camera-style JPEG."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.zeros((h, w, 3), np.float32)
    img[..., 0] = 90 + 80 * xx / w
    img[..., 1] = 110 + 60 * yy / h
    img[..., 2] = 160 - 70 * xx / w
    for _ in range(12):
        cx, cy, r = rng.uniform(0, w), rng.uniform(0, h), rng.uniform(30, 160)
        col = rng.uniform(20, 235, 3)
        m = np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * r * r)))[..., None]
        img = img * (1 - 0.8 * m) + col * 0.8 * m
    tex = np.sin(xx / 3.1) * np.cos(yy / 4.7) * 6
    img += tex[..., None]
    img += rng.normal(0, 3.0, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def _jpeg_roundtrip(arr: np.ndarray, q: int) -> np.ndarray:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, "JPEG", quality=q)
    buf.seek(0)
    return np.asarray(Image.open(buf).convert("RGB"))


@pytest.fixture(scope="session")
def image_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("ml_images")
    base = _photo_like()
    clean = os.path.join(d, "clean.jpg")
    Image.fromarray(base).save(clean, "JPEG", quality=92)

    # splice: a low-quality JPEG history everywhere, then a fresh foreign patch, saved at high quality
    lq = _jpeg_roundtrip(base, 60)
    donor = _photo_like(400, 400, seed=7)
    spliced = lq.copy()
    spliced[200:380, 450:650] = donor[50:230, 60:260]
    spliced_path = os.path.join(d, "spliced.jpg")
    Image.fromarray(spliced).save(spliced_path, "JPEG", quality=95)

    # copy-move within the image
    cm = lq.copy()
    cm[60:220, 80:280] = lq[380:540, 600:800]
    cm_path = os.path.join(d, "copymove.jpg")
    Image.fromarray(cm).save(cm_path, "JPEG", quality=95)

    png = os.path.join(d, "screenshot.png")
    Image.fromarray(base[:500, :700]).save(png, "PNG")

    rgba = np.dstack([base[:300, :300], np.full((300, 300), 200, np.uint8)])
    rgba_path = os.path.join(d, "alpha.png")
    Image.fromarray(rgba, "RGBA").save(rgba_path, "PNG")

    tiny = os.path.join(d, "tiny.jpg")
    Image.fromarray(base[:60, :80]).save(tiny, "JPEG", quality=90)

    return {"dir": str(d), "clean": clean, "spliced": spliced_path, "copymove": cm_path, "png": png,
            "rgba": rgba_path, "tiny": tiny}


@pytest.fixture()
def no_deep(monkeypatch):
    monkeypatch.setenv("ML_ENABLE_DEEP", "false")
    yield
