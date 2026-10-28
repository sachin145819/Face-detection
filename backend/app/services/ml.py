"""Thin, lazy wrapper around app.ml.pipeline (the ONLY ML entry point the backend uses).

The pipeline module is imported lazily so that a heavy / broken ML import never prevents
the API from starting.
"""
import logging
import os
import threading

from app.config import get_settings

log = logging.getLogger("truthlens.ml")

_state = {"models_loaded": False, "warmup_error": None}


def export_ml_env() -> None:
    """Make settings visible to the ML package, which may read os.environ directly."""
    s = get_settings()
    os.environ.setdefault("ML_ENABLE_DEEP", "true" if s.ML_ENABLE_DEEP else "false")
    os.environ.setdefault("MODEL_CACHE_DIR", s.MODEL_CACHE_DIR)
    os.environ.setdefault("VIDEO_MAX_FRAMES", str(s.VIDEO_MAX_FRAMES))


def _pipeline():
    from app.ml import pipeline  # noqa: PLC0415 - intentional lazy import

    return pipeline


def analyze_image(image_path: str, output_dir: str) -> dict:
    return _pipeline().analyze_image(image_path, output_dir)


def restore_image(image_path: str, output_path: str, boxes=None, mask_path=None) -> dict:
    return _pipeline().restore_image(image_path, output_path, boxes=boxes, mask_path=mask_path)


class VideoUnsupportedError(RuntimeError):
    """The installed ML pipeline does not provide video support (probe_video / analyze_video)."""


def _video_fn(name: str):
    fn = getattr(_pipeline(), name, None)
    if not callable(fn):
        raise VideoUnsupportedError(f"Video analysis is not available on this server ({name} missing)")
    return fn


def probe_video(video_path: str) -> dict:
    """-> {duration_s, fps, frame_count, width, height, codec, format}; ValueError if undecodable."""
    return _video_fn("probe_video")(video_path)


def analyze_video(video_path: str, output_dir: str, max_frames: int | None = None) -> dict:
    return _video_fn("analyze_video")(video_path, output_dir, max_frames=max_frames)


def _warmup() -> None:
    try:
        p = _pipeline()
        fn = getattr(p, "warmup", None)
        if callable(fn):
            fn()
        _state["models_loaded"] = True
        log.info("ML warmup complete")
    except Exception as exc:  # never let model loading break the API
        _state["warmup_error"] = repr(exc)
        log.exception("ML warmup failed (API keeps running): %s", exc)


def start_warmup_thread() -> threading.Thread:
    t = threading.Thread(target=_warmup, name="ml-warmup", daemon=True)
    t.start()
    return t


def models_loaded() -> bool:
    return bool(_state["models_loaded"])
