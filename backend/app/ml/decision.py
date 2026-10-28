"""Decision engine: weighted fusion of the available signals -> verdict, score, confidence, text."""
from __future__ import annotations

from .utils import clamp01

# Base weights (renormalised over the signals that are available for a given image).
WEIGHTS = {
    "metadata": 0.08,
    "ela": 0.20,
    "noise": 0.14,
    "frequency": 0.08,
    "deepfake": 0.25,
    "ai_generated": 0.25,
}
LABELS = {
    "metadata": "Metadata (EXIF) analysis",
    "ela": "Error Level Analysis",
    "noise": "Noise residual consistency",
    "frequency": "Frequency-domain artifacts",
    "deepfake": "Deepfake face analysis",
    "ai_generated": "AI-generated image detector",
}
SIGNAL_ORDER = ["metadata", "ela", "noise", "frequency", "deepfake", "ai_generated"]

# Verdict thresholds
DEEPFAKE_THRESHOLD = 0.70        # max face deepfake probability -> "deepfake"
AI_GENERATED_THRESHOLD = 0.80    # whole-image AI probability -> "ai_generated"
METADATA_AI_PROB = 0.90          # implied AI probability when metadata names a generator
MANIPULATED_THRESHOLD = 0.60     # combined local-tampering evidence (ELA / noise) -> "manipulated"
FUSED_SUSPICION_THRESHOLD = 0.55 # overall fused suspicion -> "manipulated" even without one strong cue
EDITOR_CORROBORATION = 0.05      # editing software in metadata nudges tampering evidence (if already > 0.4)
# Borderline bands used for the uncertainty note
DEEPFAKE_BORDERLINE = 0.45
AI_BORDERLINE = 0.50
STRONG_SIGNAL = 0.60
CLEAN_SIGNAL = 0.15
# Score ranges per verdict
AUTHENTIC_MIN_SCORE = 55.0
NON_AUTHENTIC_MAX_SCORE = 45.0
MIN_SCORE = 2.0
MAX_CONFIDENCE = 0.95            # never claim certainty


def _tamper_evidence(scores: dict, avail: dict, editor: bool) -> float:
    vals = [scores[k] for k in ("ela", "noise") if avail.get(k)]
    if not vals:
        return 0.0
    t = 0.75 * max(vals) + 0.25 * (sum(vals) / len(vals))
    if editor and t > 0.4:
        t += EDITOR_CORROBORATION
    return clamp01(t)


def decide(signals: dict, ctx: dict) -> dict:
    """signals: key -> signal dict (score, available). ctx: extra context (see pipeline)."""
    avail = {k: bool(signals[k]["available"]) for k in SIGNAL_ORDER}
    scores = {k: float(signals[k]["score"]) for k in SIGNAL_ORDER}
    total_w = sum(WEIGHTS[k] for k in SIGNAL_ORDER if avail[k])
    eff_w = {k: (WEIGHTS[k] / total_w if avail[k] and total_w > 0 else 0.0) for k in SIGNAL_ORDER}
    fused = sum(eff_w[k] * scores[k] for k in SIGNAL_ORDER)

    df = scores["deepfake"] if avail["deepfake"] else None
    ai = scores["ai_generated"] if avail["ai_generated"] else None
    meta_ai = bool(ctx.get("metadata_ai_hint"))
    tamper = _tamper_evidence(scores, avail, bool(ctx.get("editor")))

    candidates = []
    if df is not None and df >= DEEPFAKE_THRESHOLD:
        candidates.append(("deepfake", df))
    ai_p = max(ai or 0.0, METADATA_AI_PROB if meta_ai else 0.0)
    if (ai is not None and ai >= AI_GENERATED_THRESHOLD) or meta_ai:
        candidates.append(("ai_generated", ai_p))

    if candidates:
        # Prefer the specific label with the higher probability; on a tie a fully generated image wins.
        candidates.sort(key=lambda c: (c[1], c[0] == "ai_generated"), reverse=True)
        verdict, p = candidates[0]
    elif tamper >= MANIPULATED_THRESHOLD:
        verdict, p = "manipulated", tamper
    elif fused >= FUSED_SUSPICION_THRESHOLD:
        verdict, p = "manipulated", fused
    else:
        verdict, p = "authentic", 1.0 - fused

    # --- authenticity score (100 = authentic) ---
    base = 100.0 * (1.0 - fused)
    if verdict == "authentic":
        # map the possible fused range [0, FUSED_SUSPICION_THRESHOLD) onto [AUTHENTIC_MIN_SCORE, 100]
        frac = clamp01(fused / FUSED_SUSPICION_THRESHOLD)
        score = 100.0 - frac * (100.0 - AUTHENTIC_MIN_SCORE)
    else:
        score = min(base, NON_AUTHENTIC_MAX_SCORE, 100.0 * (1.0 - p) + 5.0)
        score = max(MIN_SCORE, score)

    # --- coverage: how much of the applicable evidence could actually be computed ---
    applicable = [k for k in SIGNAL_ORDER if not (k == "deepfake" and ctx.get("faces_detected", 0) == 0)]
    cov = sum(WEIGHTS[k] for k in applicable if avail[k]) / max(1e-9, sum(WEIGHTS[k] for k in applicable))

    strong = [k for k in ("ela", "noise", "deepfake", "ai_generated") if avail[k] and scores[k] >= STRONG_SIGNAL]
    clean = [k for k in ("ela", "noise", "deepfake", "ai_generated") if avail[k] and scores[k] <= CLEAN_SIGNAL]

    if verdict == "authentic":
        peak = max([scores[k] for k in ("ela", "noise", "deepfake", "ai_generated") if avail[k]] or [0.0])
        conf = (1.0 - 0.5 * fused - 0.5 * peak) * (0.4 + 0.6 * cov)
    else:
        conf = p * (0.75 + 0.25 * cov)
        # the specific detectors are independent of the forensic cues; agreement raises confidence
        if verdict in ("deepfake", "ai_generated") and tamper >= MANIPULATED_THRESHOLD:
            conf += 0.03
        if verdict == "manipulated" and len(strong) >= 2:
            conf += 0.05
    conf = max(0.05, min(MAX_CONFIDENCE, conf))

    summary = _summary(verdict, p, scores, avail, ctx, strong)
    note = _uncertainty(verdict, fused, scores, avail, ctx, strong, clean, df, ai)

    return {
        "verdict": verdict,
        "authenticity_score": round(float(score), 1),
        "confidence": round(float(conf), 3),
        "summary": summary,
        "uncertainty_note": note,
        "weights": {k: round(eff_w[k], 4) for k in SIGNAL_ORDER},
        "fused_suspicion": round(float(fused), 4),
        "tamper_evidence": round(float(tamper), 4),
    }


def _summary(verdict: str, p: float, scores: dict, avail: dict, ctx: dict, strong: list) -> str:
    pct = f"{min(p, 0.99) * 100:.0f}%"
    if verdict == "deepfake":
        n = ctx.get("faces_analyzed", 1)
        who = "A face" if n > 1 else "The face"
        return (f"{who} in this image shows the visual fingerprints of deepfake or face-swap synthesis "
                f"(about {pct} likely). The marked face box shows where the model found the strongest evidence.")
    if verdict == "ai_generated":
        if ctx.get("metadata_ai_hint") and not (avail["ai_generated"] and scores["ai_generated"] >= AI_GENERATED_THRESHOLD):
            return ("The file's metadata names an AI image generator, so this picture was most likely created "
                    "by AI rather than taken with a camera.")
        extra = " Its metadata also names an AI generator." if ctx.get("metadata_ai_hint") else ""
        return (f"This image appears to have been created by an AI image generator rather than a camera "
                f"(about {pct} likely).{extra}")
    if verdict == "manipulated":
        reasons = []
        if "ela" in strong or scores["ela"] >= 0.5:
            reasons.append("uneven compression traces")
        if "noise" in strong or scores["noise"] >= 0.5:
            reasons.append("inconsistent camera noise")
        if ctx.get("editor"):
            reasons.append(f"editing software in the metadata ({ctx['editor']})")
        why = " and ".join(reasons[:2]) if reasons else "several weak forensic cues"
        return (f"Parts of this image appear to have been edited: we found {why}. "
                "The highlighted boxes mark the areas most likely to have been altered.")
    # authentic
    df = scores["deepfake"] if avail["deepfake"] else None
    if df is not None and df >= DEEPFAKE_BORDERLINE:
        return ("No clear signs of editing or AI generation were found, but one face is borderline for the "
                f"deepfake detector ({df * 100:.0f}%), so the image is probably authentic but deserves a closer look.")
    if ctx.get("deep_disabled") or not (avail["ai_generated"]):
        return ("No signs of editing were found by the forensic checks, and the image looks like an ordinary "
                "photo. AI-generation could not be checked, so treat this as a partial result.")
    return ("No significant signs of editing, face-swapping or AI generation were found; the image is "
            "consistent with an unmodified photograph.")


def _uncertainty(verdict, fused, scores, avail, ctx, strong, clean, df, ai) -> str:
    notes = []
    if ctx.get("deep_disabled"):
        notes.append("Deep-learning detectors are disabled on this server, so AI-generated images and deepfakes "
                     "cannot be reliably recognised; only classical forensics were used.")
    else:
        missing = [LABELS[k] for k in ("ai_generated", "deepfake")
                   if not avail[k] and ctx.get("model_errors", {}).get(k)]
        if missing:
            notes.append("Some detectors could not run (" + ", ".join(missing) + "), lowering confidence.")
    # Disagreement worth surfacing (ELA/noise vs. AI detectors are complementary, so their silence
    # about each other's specialty is not reported as a conflict).
    strong_forensic = [k for k in strong if k in ("ela", "noise")]   # model borderlines have their own notes
    if verdict == "authentic" and strong_forensic:
        notes.append("Signals disagree: " + ", ".join(LABELS[k] for k in strong_forensic) + " raised a flag, but the "
                     "remaining evidence was not strong enough to call the image fake.")
    if (verdict == "ai_generated" and ctx.get("metadata_ai_hint") and ai is not None and ai <= CLEAN_SIGNAL):
        notes.append("Signals disagree: the metadata names an AI generator, but the visual AI detector finds the "
                     "picture camera-like (the metadata may have been added or the image heavily edited).")
    if verdict == "manipulated" and "ela" in strong and "noise" in strong:
        notes.append("Two independent forensic checks (compression and noise) agree on the edited areas.")
    if verdict == "deepfake" and ai is not None and ai >= AI_GENERATED_THRESHOLD:
        notes.append("The whole-image AI detector also flags this picture, so it may be entirely AI-generated "
                     "rather than a face swap.")
    if verdict == "ai_generated" and df is not None and df >= DEEPFAKE_THRESHOLD:
        notes.append("A face is also flagged by the deepfake model; the face may be synthetic as part of a fully "
                     "generated image.")
    if df is not None and DEEPFAKE_BORDERLINE <= df < DEEPFAKE_THRESHOLD:
        notes.append(f"One face is borderline for the deepfake model ({df * 100:.0f}%); real faces with heavy "
                     "make-up, filters or beauty retouching can look like this.")
    if ai is not None and AI_BORDERLINE <= ai < AI_GENERATED_THRESHOLD and verdict != "ai_generated":
        notes.append(f"The AI-image detector is undecided ({ai * 100:.0f}%); heavy filters, upscaling or "
                     "digital art can confuse it.")
    if verdict == "authentic" and 0.35 <= fused < FUSED_SUSPICION_THRESHOLD:
        notes.append("The overall result is close to the decision boundary.")
    if ctx.get("faces_detected", 0) == 0 and not ctx.get("deep_disabled"):
        notes.append("No faces were found, so the face-deepfake check did not apply.")
    if ctx.get("min_side", 9999) < 400:
        notes.append("The image resolution is low, which removes many forensic traces.")
    q = ctx.get("jpeg_quality")
    if q is not None and q < 70:
        notes.append(f"The image is heavily compressed (JPEG quality ≈{q:.0f}), which can hide or mimic editing traces.")
    if ctx.get("lossless"):
        notes.append(f"{ctx.get('format')} files have no JPEG history, so compression-based checks are less informative.")
    if ctx.get("editor") and verdict == "authentic":
        notes.append(f"The file was saved by editing software ({ctx['editor']}); this is often harmless "
                     "(cropping, colour correction) and no local tampering traces were found.")
    if not ctx.get("camera_metadata") and verdict == "authentic" and not ctx.get("lossless"):
        notes.append("Camera metadata is missing (common after sharing on social media), so provenance can't be confirmed.")
    notes.append("All results are probabilistic evidence, not proof.")
    return " ".join(notes)
