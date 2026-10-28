"""Face detection with OpenCV only (no mediapipe).

Primary: YuNet (cv2.FaceDetectorYN, ~230 KB ONNX) cached in MODEL_CACHE_DIR/opencv/.
Fallback: the Haar cascade bundled with opencv-python (cv2.data.haarcascades).
"""
from __future__ import annotations

import logging
import os
import threading
import urllib.request

import cv2
import numpy as np

from ..utils import model_cache_dir, resize_max

log = logging.getLogger(__name__)

YUNET_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
             "face_detection_yunet_2023mar.onnx")
YUNET_FILE = "face_detection_yunet_2023mar.onnx"
DETECT_MAX_SIDE = 1024
YUNET_SCORE_THRESHOLD = 0.75
YUNET_NMS_THRESHOLD = 0.3
MIN_FACE_PX = 20          # at detection scale
MAX_FACES = 10

_lock = threading.Lock()
_tls = threading.local()
_state: dict = {"yunet_path": None, "haar": None, "tried_download": False}


def yunet_path(download: bool = True) -> str | None:
    path = os.path.join(model_cache_dir(), "opencv", YUNET_FILE)
    if os.path.isfile(path) and os.path.getsize(path) > 100_000:
        return path
    if not download:
        return None
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".part"
        urllib.request.urlretrieve(YUNET_URL, tmp)
        os.replace(tmp, path)
        return path if os.path.getsize(path) > 100_000 else None
    except Exception as exc:  # offline etc.
        log.warning("YuNet download failed (%s); using Haar cascade fallback", exc)
        return None


def _get_haar():
    if _state["haar"] is None:
        try:
            p = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
            c = cv2.CascadeClassifier(p)
            _state["haar"] = c if not c.empty() else False
        except Exception:
            _state["haar"] = False
    return _state["haar"] or None


def warmup() -> str:
    with _lock:
        if _state["yunet_path"] is None and not _state["tried_download"]:
            _state["tried_download"] = True
            _state["yunet_path"] = yunet_path(download=True)
    return "yunet" if _state["yunet_path"] else "haar"


def detect_faces(rgb: np.ndarray) -> tuple[list[dict], str]:
    """Return ([{box:[x,y,w,h], score}], detector_name) in the coordinates of `rgb`."""
    warmup()
    small, s = resize_max(rgb, DETECT_MAX_SIDE)
    bgr = cv2.cvtColor(small, cv2.COLOR_RGB2BGR)
    h, w = bgr.shape[:2]
    faces: list[dict] = []
    method = "none"
    path = _state["yunet_path"]
    if path:
        try:
            # One detector per thread (FaceDetectorYN keeps mutable state such as the input size).
            det = getattr(_tls, "yunet", None)
            if det is None:
                det = cv2.FaceDetectorYN.create(path, "", (w, h), YUNET_SCORE_THRESHOLD, YUNET_NMS_THRESHOLD, 5000)
                _tls.yunet = det
            det.setInputSize((w, h))
            _, out = det.detect(bgr)
            method = "yunet"
            if out is not None:
                for row in out:
                    x, y, bw, bh = [float(v) for v in row[:4]]
                    if min(bw, bh) < MIN_FACE_PX:
                        continue
                    faces.append({"box": [x, y, bw, bh], "score": float(row[-1])})
        except Exception as exc:
            log.warning("YuNet detection failed: %s", exc)
            method = "none"
    if method == "none":
        haar = _get_haar()
        if haar is not None:
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            rects = haar.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6,
                                          minSize=(max(MIN_FACE_PX, 24), max(MIN_FACE_PX, 24)))
            method = "haar"
            for (x, y, bw, bh) in rects:
                faces.append({"box": [float(x), float(y), float(bw), float(bh)], "score": 0.8})
    inv = 1.0 / s
    H, W = rgb.shape[:2]
    out_faces = []
    for f in sorted(faces, key=lambda f: f["box"][2] * f["box"][3], reverse=True)[:MAX_FACES]:
        x, y, bw, bh = [v * inv for v in f["box"]]
        x0, y0 = max(0, int(round(x))), max(0, int(round(y)))
        x1, y1 = min(W, int(round(x + bw))), min(H, int(round(y + bh)))
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        out_faces.append({"box": [x0, y0, x1 - x0, y1 - y0], "score": round(float(f["score"]), 4)})
    return out_faces, method


def crop_face(rgb: np.ndarray, box: list[int], margin: float = 0.2) -> tuple[np.ndarray, list[int]]:
    """Square crop around the face with a relative margin (clipped to the image)."""
    H, W = rgb.shape[:2]
    x, y, w, h = box
    cx, cy = x + w / 2.0, y + h / 2.0
    side = max(w, h) * (1.0 + 2 * margin)
    x0, y0 = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
    x1, y1 = int(min(W, cx + side / 2)), int(min(H, cy + side / 2))
    return rgb[y0:y1, x0:x1], [x0, y0, x1 - x0, y1 - y0]
