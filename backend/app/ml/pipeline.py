"""TruthLens ML pipeline — the ONLY module the backend imports (see docs/CONTRACT.md §4).

    analyze_image(image_path, output_dir) -> dict
    restore_image(image_path, output_path, boxes=None, mask_path=None) -> dict
    warmup() -> None
    probe_video(video_path) -> dict                               (§6, implemented in video.py)
    analyze_video(video_path, output_dir, max_frames=None) -> dict (§6, implemented in video.py)

Stages: preprocessing -> classical forensics (metadata, ELA, noise, frequency) -> face detection ->
deep detectors (deepfake per face, AI-generated whole image; only if ML_ENABLE_DEEP != "false") ->
explainability (suspicion heatmap, regions) -> decision engine (weighted fusion).
torch/transformers are imported lazily, so ML_ENABLE_DEEP=false never loads them.
"""
from __future__ import annotations

import logging
import os
import tempfile
import time
import warnings

from . import decision, explain
from .detectors import faces as face_det
from .detectors.ai_generated import analyze_ai_generated
from .detectors.deepfake import analyze_faces
from .forensics.ela import analyze_ela
from .forensics.frequency import analyze_frequency
from .forensics.metadata import analyze_metadata
from .forensics.noise import analyze_noise
from .preprocessing import load_image
from .restoration import restore
from .utils import deep_enabled, to_py
from .video import analyze_video, probe_video  # noqa: F401  (re-exported for the backend, CONTRACT §6.2)

log = logging.getLogger(__name__)

PIPELINE_VERSION = "truthlens-ml-1.0"
HEATMAP_NAME = "heatmap.png"
ELA_NAME = "ela.png"
_PUBLIC_SIGNAL_KEYS = ("key", "label", "score", "weight", "available", "explanation", "details")


def warmup() -> None:
    """Preload the face detector and (if enabled) the deep models. Safe to call repeatedly / in a thread."""
    try:
        face_det.warmup()
    except Exception as exc:  # pragma: no cover
        log.warning("face detector warmup failed: %s", exc)
    if deep_enabled():
        try:
            from .detectors.models import warmup_all
            status = warmup_all()
            log.info("ML warmup: %s", status)
        except Exception as exc:  # never crash the server
            log.warning("deep model warmup failed: %s", exc)


def models_loaded() -> bool:
    """True when every deep model is in memory (False when deep models are disabled)."""
    if not deep_enabled():
        return False
    try:
        from .detectors.models import models_loaded as _ml
        return _ml()
    except Exception:
        return False


def _failed_signal(key: str, exc: Exception) -> dict:
    return {"key": key, "label": decision.LABELS[key], "score": 0.0, "available": False,
            "explanation": f"This check failed on this image ({type(exc).__name__}) and was skipped.",
            "details": {"error": str(exc)[:200]}}


def _run(key: str, fn, *args):
    try:
        return fn(*args)
    except Exception as exc:
        log.exception("%s analysis failed", key)
        return _failed_signal(key, exc)


def _analyze(image_path: str, output_dir: str | None, write_files: bool = True):
    t0 = time.perf_counter()
    if write_files and output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            img = load_image(image_path)
        except Exception as exc:
            raise ValueError(f"Unsupported or corrupt image: {exc}") from exc

    deep = deep_enabled()
    ela_path = os.path.abspath(os.path.join(output_dir, ELA_NAME)) if (write_files and output_dir) else None
    heat_path = os.path.abspath(os.path.join(output_dir, HEATMAP_NAME)) if (write_files and output_dir) else None

    meta = _run("metadata", analyze_metadata, img)
    ela = _run("ela", analyze_ela, img, ela_path)
    noise = _run("noise", analyze_noise, img)
    freq = _run("frequency", analyze_frequency, img)
    if ela_path and not os.path.isfile(ela_path):
        ela_path = None

    try:
        faces, detector = face_det.detect_faces(img.rgb)
    except Exception as exc:
        log.warning("face detection failed: %s", exc)
        faces, detector = [], "failed"
    try:
        df_sig, faces_out = analyze_faces(img.rgb, faces, detector)
    except Exception as exc:
        log.exception("deepfake analysis failed")
        df_sig = _failed_signal("deepfake", exc)
        faces_out = [{"box": f["box"], "deepfake_probability": None, "analyzed": False} for f in faces]
    try:
        ai_sig, ai_cam = analyze_ai_generated(img.rgb)
    except Exception as exc:
        log.exception("AI-generated analysis failed")
        ai_sig, ai_cam = _failed_signal("ai_generated", exc), None

    signals = {"metadata": meta, "ela": ela, "noise": noise, "frequency": freq,
               "deepfake": df_sig, "ai_generated": ai_sig}

    model_versions = {"deepfake": None, "ai_generated": None}
    model_errors = {}
    if deep:
        from .detectors.models import get_model
        for k in ("deepfake", "ai_generated"):
            m = get_model(k)
            model_versions[k] = m.id if m.available else None
            if m.error:
                model_errors[k] = m.error

    lossless = img.format in ("PNG", "WEBP", "BMP", "TIFF", "GIF")
    ctx = {
        "metadata_ai_hint": bool(meta.get("_ai_hint")),
        "editor": (meta.get("_software") or meta.get("_editor")) if meta.get("_editor") else None,
        "faces_detected": len(faces_out),
        "faces_analyzed": sum(1 for f in faces_out if f.get("analyzed")),
        "deep_disabled": not deep,
        "model_errors": model_errors,
        "min_side": min(img.width, img.height),
        "jpeg_quality": img.jpeg_quality,
        "lossless": lossless,
        "format": img.format,
        "camera_metadata": bool((meta.get("details") or {}).get("camera_present")),
    }
    dec = decision.decide(signals, ctx)

    # ---- explainability ----
    scores = {k: float(signals[k]["score"]) for k in signals if signals[k].get("available")}
    ai_score = float(ai_sig["score"]) if ai_sig.get("available") else None
    regions = []
    regions += ela.get("_regions", [])
    regions += noise.get("_regions", [])
    regions += explain.cam_regions(img.width, img.height, faces_out, ai_score, ai_cam)
    regions = explain.merge_regions(regions, img.width, img.height)
    sus_map = None
    try:
        sus_map, _ = explain.build_suspicion_map(img.width, img.height, ela, noise, faces_out, ai_score,
                                                 ai_cam, scores)
        if heat_path:
            explain.render_heatmap(img.rgb, sus_map, regions, faces_out, heat_path)
    except Exception:
        log.exception("heatmap rendering failed")
        heat_path = None
    if heat_path and not os.path.isfile(heat_path):
        heat_path = None

    # ---- assemble the public result ----
    out_signals = []
    for k in decision.SIGNAL_ORDER:
        s = dict(signals[k])
        s["key"] = k
        s.setdefault("label", decision.LABELS[k])
        s["weight"] = dec["weights"][k]
        s["score"] = round(float(s.get("score") or 0.0), 4)
        s["details"] = s.get("details") or {}
        out_signals.append({kk: s.get(kk) for kk in _PUBLIC_SIGNAL_KEYS})

    public_faces = []
    for f in faces_out:
        p = f.get("deepfake_probability")
        public_faces.append({"box": [int(v) for v in f["box"]],
                             "deepfake_probability": None if p is None else round(float(p), 4),
                             "analyzed": bool(f.get("analyzed")),
                             "detection_score": f.get("detection_score")})

    result = {
        "verdict": dec["verdict"],
        "authenticity_score": dec["authenticity_score"],
        "confidence": dec["confidence"],
        "uncertainty_note": dec["uncertainty_note"],
        "summary": dec["summary"],
        "signals": out_signals,
        "faces": public_faces,
        "regions": regions,
        "metadata": {
            "format": img.format,
            "width": img.width,
            "height": img.height,
            "exif": meta.get("_exif") or {},
            "software": meta.get("_software"),
            "mode": img.mode,
            "file_size": img.file_size,
            "jpeg_quality_estimate": img.jpeg_quality,
            "exif_orientation": img.orientation,
        },
        "heatmap_path": heat_path,
        "ela_path": ela_path,
        "processing_ms": 0,
        "model_versions": model_versions,
        "fusion": {"fused_suspicion": dec["fused_suspicion"], "tamper_evidence": dec["tamper_evidence"],
                   "pipeline_version": PIPELINE_VERSION, "deep_enabled": deep,
                   "face_detector": detector},
    }
    result["processing_ms"] = int(round((time.perf_counter() - t0) * 1000))
    return to_py(result), sus_map


def analyze_image(image_path: str, output_dir: str) -> dict:
    result, _ = _analyze(image_path, output_dir, write_files=True)
    return result


def restore_image(image_path: str, output_path: str,
                  boxes: list[list[int]] | None = None,
                  mask_path: str | None = None) -> dict:
    def auto_regions(path: str):
        with tempfile.TemporaryDirectory() as td:
            res, sus_map = _analyze(path, td, write_files=False)
        return res["regions"], sus_map

    return to_py(restore(image_path, output_path, boxes, mask_path, auto_regions))
