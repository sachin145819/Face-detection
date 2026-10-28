"""Image loading / normalisation shared by every analysis step.

All outputs (boxes, maps) are expressed in the *displayed* orientation, i.e. after applying the
EXIF Orientation tag — that is how browsers render the image, so frontend overlays line up.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image, ImageOps

Image.MAX_IMAGE_PIXELS = 200_000_000  # we cap upload size elsewhere; avoid DecompressionBombWarning noise

# Standard IJG (libjpeg) luminance quantisation table (quality 50), natural order.
_STD_LUMA = np.array([
    16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55,
    14, 13, 16, 24, 40, 57, 69, 56, 14, 17, 22, 29, 51, 87, 80, 62,
    18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92,
    49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99,
], dtype=np.float64)


@dataclass
class LoadedImage:
    path: str
    format: str
    mode: str
    width: int                # displayed (oriented) width
    height: int               # displayed (oriented) height
    orientation: int          # EXIF orientation tag (1 = normal)
    raw_rgb: np.ndarray       # decoded pixels in *stored* orientation (for JPEG-grid aware ELA)
    rgb: np.ndarray           # decoded pixels in displayed orientation, uint8 HxWx3
    gray: np.ndarray          # float32 HxW, displayed orientation
    info: dict = field(default_factory=dict)
    pil_exif: object = None
    jpeg_quality: float | None = None
    has_alpha: bool = False
    n_frames: int = 1
    file_size: int = 0
    head_bytes: bytes = b""


def estimate_jpeg_quality(img: Image.Image) -> float | None:
    """Estimate the IJG quality factor (1-100) from the luminance quantisation table."""
    try:
        q = getattr(img, "quantization", None)
        if not q:
            return None
        table = np.array(q.get(0, list(q.values())[0]), dtype=np.float64)
        if table.size != 64:
            return None
        # PIL returns the table in zig-zag order on some versions; compare the sorted-ish mean ratio,
        # which is order independent enough for an estimate.
        s = float(np.mean(table) / np.mean(_STD_LUMA) * 100.0)
        if s <= 0:
            return None
        quality = (200.0 - s) / 2.0 if s <= 100 else 5000.0 / s
        return float(max(1.0, min(100.0, round(quality, 1))))
    except Exception:
        return None


def apply_orientation(arr: np.ndarray, orientation: int) -> np.ndarray:
    """Apply an EXIF orientation to a numpy image (same mapping as PIL.ImageOps.exif_transpose)."""
    if orientation == 2:
        return arr[:, ::-1]
    if orientation == 3:
        return arr[::-1, ::-1]
    if orientation == 4:
        return arr[::-1, :]
    if orientation == 5:
        return np.swapaxes(arr, 0, 1)
    if orientation == 6:
        return np.rot90(arr, -1)
    if orientation == 7:
        return np.swapaxes(arr[::-1, ::-1], 0, 1)
    if orientation == 8:
        return np.rot90(arr, 1)
    return arr


def load_image(path: str) -> LoadedImage:
    with open(path, "rb") as f:
        data = f.read()
    with Image.open(path) as img:
        fmt = (img.format or "UNKNOWN").upper()
        mode = img.mode
        n_frames = int(getattr(img, "n_frames", 1) or 1)
        info = dict(img.info or {})
        try:
            exif = img.getexif()
        except Exception:
            exif = None
        orientation = 1
        try:
            orientation = int(exif.get(0x0112, 1)) if exif else 1
        except Exception:
            orientation = 1
        if orientation not in range(1, 9):
            orientation = 1
        jpeg_q = estimate_jpeg_quality(img) if fmt in ("JPEG", "MPO") else None
        img.seek(0)
        has_alpha = mode in ("RGBA", "LA", "PA") or (mode == "P" and "transparency" in info)
        if has_alpha:
            rgba = img.convert("RGBA")
            bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            rgb_img = Image.alpha_composite(bg, rgba).convert("RGB")
        else:
            rgb_img = img.convert("RGB")
        raw = np.asarray(rgb_img, dtype=np.uint8).copy()

    rgb = np.ascontiguousarray(apply_orientation(raw, orientation))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    h, w = rgb.shape[:2]
    return LoadedImage(
        path=path, format=fmt, mode=mode, width=int(w), height=int(h), orientation=orientation,
        raw_rgb=raw, rgb=rgb, gray=gray, info=info, pil_exif=exif, jpeg_quality=jpeg_q,
        has_alpha=has_alpha, n_frames=n_frames, file_size=len(data),
        head_bytes=data[:262144] + (data[-65536:] if len(data) > 262144 else b""),
    )


def oriented_pil(path: str) -> Image.Image:
    """Return an RGB PIL image in displayed orientation (used by restoration)."""
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
            rgba = img.convert("RGBA")
            bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            return Image.alpha_composite(bg, rgba).convert("RGB")
        return img.convert("RGB")
