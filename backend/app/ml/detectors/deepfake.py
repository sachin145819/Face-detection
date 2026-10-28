"""Per-face deepfake classification."""
from __future__ import annotations

import numpy as np
from PIL import Image

from ..utils import clamp01, deep_enabled
from .faces import crop_face
from .models import get_model

MIN_FACE_FOR_CLASSIFIER = 40     # px (original image) — smaller faces are listed but not classified
SMALL_FACE_PX = 96               # faces below this are less reliable: probabilities shrink toward 0.5
SMALL_FACE_SHRINK = 0.6
FACE_MARGIN = 0.3                # matches the framing of the training crops (tuned on 50 faces)


def unavailable_signal(explanation: str, details: dict | None = None) -> dict:
    return {"key": "deepfake", "label": "Deepfake face analysis", "score": 0.0, "available": False,
            "explanation": explanation, "details": details or {}}


def analyze_faces(rgb: np.ndarray, faces: list[dict], detector: str) -> tuple[dict, list[dict]]:
    """Returns (signal, faces_out). faces_out items: box, deepfake_probability (float|None), plus
    internal keys prefixed with '_' (CAM grid, crop box) that the pipeline strips before returning."""
    faces_out = [{"box": f["box"], "deepfake_probability": None, "detection_score": f["score"],
                  "analyzed": False} for f in faces]
    base_details = {"faces_detected": len(faces), "face_detector": detector}
    if not faces:
        return unavailable_signal("No faces were detected, so the face-deepfake check does not apply.",
                                  base_details), faces_out
    if not deep_enabled():
        return unavailable_signal("Deep-learning models are disabled on this server (ML_ENABLE_DEEP=false); "
                                  "faces were located but not checked for deepfakes.", base_details), faces_out
    model = get_model("deepfake")
    if not model.load():
        return unavailable_signal("The deepfake model is not available on this server (offline or not downloaded), "
                                  "so the detected faces were not checked.",
                                  {**base_details, "model": model.id, "error": model.error}), faces_out

    crops, idx, crop_boxes = [], [], []
    for i, f in enumerate(faces):
        if min(f["box"][2], f["box"][3]) < MIN_FACE_FOR_CLASSIFIER:
            continue
        crop, cbox = crop_face(rgb, f["box"], FACE_MARGIN)
        if crop.size == 0:
            continue
        crops.append(Image.fromarray(np.ascontiguousarray(crop)))
        idx.append(i)
        crop_boxes.append(cbox)
    if not crops:
        return unavailable_signal("Faces were found but they are too small to analyse reliably for deepfakes.",
                                  base_details), faces_out
    try:
        probs, cams = model.predict(crops)
    except Exception as exc:
        return unavailable_signal(f"The deepfake model failed on this image ({type(exc).__name__}).",
                                  base_details), faces_out

    for j, i in enumerate(idx):
        p = probs[j]
        size = min(faces[i]["box"][2], faces[i]["box"][3])
        if size < SMALL_FACE_PX:
            p = 0.5 + (p - 0.5) * SMALL_FACE_SHRINK
        faces_out[i]["deepfake_probability"] = round(clamp01(p), 4)
        faces_out[i]["analyzed"] = True
        faces_out[i]["_cam"] = cams[j]
        faces_out[i]["_crop_box"] = crop_boxes[j]

    analysed = [f for f in faces_out if f["analyzed"]]
    top = max(analysed, key=lambda f: f["deepfake_probability"])
    score = float(top["deepfake_probability"])
    n = len(analysed)
    if score >= 0.7:
        expl = (f"The face-forensics model rates {'a face' if n > 1 else 'the face'} as likely synthetic or "
                f"swapped ({score * 100:.0f}% deepfake probability).")
    elif score >= 0.45:
        expl = f"The face-forensics model is unsure about {'one of the faces' if n > 1 else 'the face'} ({score * 100:.0f}% deepfake probability)."
    else:
        expl = (f"{n} face{'s' if n > 1 else ''} analysed; none show deepfake characteristics "
                f"(highest probability {score * 100:.0f}%).")
    return {
        "key": "deepfake", "label": "Deepfake face analysis", "score": score, "available": True,
        "explanation": expl,
        "details": {**base_details, "faces_analyzed": n, "model": model.id,
                    "per_face": [f["deepfake_probability"] for f in analysed]},
    }, faces_out
