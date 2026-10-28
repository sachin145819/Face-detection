"""Frequency-domain analysis.

GAN / diffusion decoders build images with transposed convolutions or fixed-factor upsampling,
which leaves small periodic patterns. These show up as isolated bright peaks in the Fourier spectrum
of the high-pass residual (camera images have a smooth, peak-free residual spectrum). JPEG's 8x8
blocking produces peaks on a regular N/8 lattice, so for JPEG files that lattice is ignored.
This is a weak, supporting signal and is weighted low in the fusion.
"""
from __future__ import annotations

import cv2
import numpy as np
from scipy.ndimage import maximum_filter, median_filter

from ..preprocessing import LoadedImage
from ..utils import clamp01

FFT_CROP = 512
FFT_MIN_CROP = 128
PEAK_Z_MID = 7.0        # robust z of the strongest periodic peaks giving score 0.5
PEAK_Z_SCALE = 1.5
LOW_FREQ_RADIUS = 0.06  # fraction of N excluded around DC
AXIS_BAND = 2


def _crops(gray: np.ndarray, n: int) -> list[np.ndarray]:
    h, w = gray.shape
    ys = [(h - n) // 2, 0, 0, h - n, h - n]
    xs = [(w - n) // 2, 0, w - n, 0, w - n]
    out = []
    for y, x in zip(ys, xs):
        out.append(gray[y:y + n, x:x + n])
    return out


def _residual_spectrum(crop: np.ndarray) -> np.ndarray:
    c = crop.astype(np.float32)
    res = c - cv2.GaussianBlur(c, (0, 0), 1.0)
    win = np.outer(np.hanning(c.shape[0]), np.hanning(c.shape[1])).astype(np.float32)
    f = np.fft.fftshift(np.fft.fft2(res * win))
    return np.log1p(np.abs(f)).astype(np.float32)


def analyze_frequency(img: LoadedImage) -> dict:
    gray = img.gray
    m = min(gray.shape)
    n = FFT_CROP
    while n > m and n > FFT_MIN_CROP:
        n //= 2
    if n > m:
        return {
            "key": "frequency", "label": "Frequency-domain artifacts", "score": 0.0, "available": False,
            "explanation": "Image is too small for frequency analysis.", "details": {},
        }
    crops = _crops(gray, n) if min(gray.shape) >= n * 1.5 else [_crops(gray, n)[0]]
    spec = np.mean([_residual_spectrum(c) for c in crops], axis=0)

    bg = median_filter(spec, size=9, mode="reflect")
    excess = spec - bg
    cy = cx = n // 2
    yy, xx = np.mgrid[0:n, 0:n]
    r = np.hypot(yy - cy, xx - cx)
    valid = (r > LOW_FREQ_RADIUS * n) & (np.abs(yy - cy) > AXIS_BAND) & (np.abs(xx - cx) > AXIS_BAND)
    vals = excess[valid]
    med = float(np.median(vals))
    mad = float(np.median(np.abs(vals - med))) * 1.4826 + 1e-6
    zmap = (excess - med) / mad

    # JPEG 8x8 lattice (peaks at multiples of N/8 in each axis)
    lattice = np.zeros_like(valid)
    step = n // 8
    for i in range(-4, 5):
        for j in range(-4, 5):
            if i == 0 and j == 0:
                continue
            y, x = cy + i * step, cx + j * step
            lattice[max(0, y - 2):y + 3, max(0, x - 2):x + 3] = True
    # Local maxima only (peaks), excluding axes and DC
    peaks = (zmap == maximum_filter(zmap, size=5)) & valid
    lat_vals = np.sort(zmap[peaks & lattice])[::-1]
    off_vals = np.sort(zmap[peaks & ~lattice])[::-1]
    lat_z = float(np.mean(lat_vals[:4])) if lat_vals.size >= 4 else 0.0
    # Periodic artifacts appear as symmetric pairs, so look at the mean of the top-6 off-lattice peaks.
    off_z = float(np.mean(off_vals[:6])) if off_vals.size >= 6 else 0.0

    is_jpeg = img.format in ("JPEG", "MPO")
    periodic_z = off_z if is_jpeg else max(off_z, lat_z)
    score = clamp01(1.0 / (1.0 + np.exp(-(periodic_z - PEAK_Z_MID) / PEAK_Z_SCALE)))
    if min(img.width, img.height) < 256:
        score *= 0.6

    # High-frequency energy ratio of the plain spectrum (context; upscaled/AI images are often low)
    c0 = crops[0].astype(np.float32)
    p = np.abs(np.fft.fftshift(np.fft.fft2(c0 - c0.mean()))) ** 2
    hf = float(p[r > 0.35 * n].sum())
    mf = float(p[(r > 0.08 * n) & (r <= 0.35 * n)].sum()) + 1e-9
    hf_ratio = hf / mf

    if score >= 0.6:
        expl = ("The frequency spectrum contains strong periodic peaks, a pattern typical of the upsampling "
                "layers used by GAN/diffusion image generators (or of resampling during editing).")
    elif score >= 0.35:
        expl = "The frequency spectrum shows some periodic structure; this is weak evidence of synthesis or resampling."
    else:
        expl = "No unusual periodic patterns were found in the frequency spectrum."
    if is_jpeg:
        expl += " (JPEG block-grid frequencies were ignored.)"

    return {
        "key": "frequency",
        "label": "Frequency-domain artifacts",
        "score": float(score),
        "available": True,
        "explanation": expl,
        "details": {
            "fft_size": n,
            "crops": len(crops),
            "offgrid_peak_z": round(off_z, 2),
            "grid_peak_z": round(lat_z, 2),
            "high_freq_energy_ratio": round(hf_ratio, 5),
        },
    }
