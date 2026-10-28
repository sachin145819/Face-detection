"""EXIF / container metadata forensics.

Metadata is weak evidence on its own (it is trivially stripped or forged), so this signal mostly
contributes context: camera provenance lowers suspicion, editing software raises it moderately and
explicit AI-generator fingerprints (PNG "parameters" chunks, C2PA "trainedAlgorithmicMedia", etc.)
raise it strongly and are also used by the decision engine as direct AI-generation evidence.
"""
from __future__ import annotations

import re

from PIL import ExifTags

# ---- calibrated suspicion levels (0-1) -------------------------------------------------------
SCORE_AI_HINT = 0.95
SCORE_EDITOR = 0.55
SCORE_NO_CAMERA_JPEG = 0.30
SCORE_NO_METADATA_LOSSLESS = 0.25   # PNG/WebP screenshots & exports usually have no EXIF: mild only
SCORE_CAMERA_CLEAN = 0.05
SCORE_PARTIAL = 0.20

EDITOR_PATTERNS = [
    r"photoshop", r"lightroom", r"\bgimp\b", r"affinity", r"pixelmator", r"paint\.net", r"corel",
    r"snapseed", r"picsart", r"facetune", r"canva", r"fotor", r"photopea", r"luminar", r"capture one",
    r"darktable", r"rawtherapee", r"krita", r"inkscape", r"meitu", r"faceapp", r"remini", r"befunky",
    r"photoscape", r"pixlr", r"airbrush", r"lensa", r"vsco", r"photodirector",
]

AI_PATTERNS = {
    r"stable[\s_-]?diffusion": "Stable Diffusion",
    r"\bsdxl\b": "Stable Diffusion XL",
    r"midjourney": "Midjourney",
    r"dall[\s·\-_]?e": "DALL-E",
    r"openai": "OpenAI",
    r"firefly": "Adobe Firefly",
    r"comfyui": "ComfyUI",
    r"automatic1111|a1111": "AUTOMATIC1111",
    r"invokeai": "InvokeAI",
    r"novelai": "NovelAI",
    r"leonardo\.?ai": "Leonardo.ai",
    r"ideogram": "Ideogram",
    r"imagen": "Google Imagen",
    r"gemini": "Google Gemini",
    r"flux\.?1|black forest labs": "FLUX",
    r"trainedalgorithmicmedia": "IPTC 'trained algorithmic media' (AI-generated) tag",
    r"compositewithtrainedalgorithmicmedia": "IPTC 'composite with AI' tag",
    r"negative prompt": "generation prompt text",
    r"sampler:\s*\w+": "diffusion sampler settings",
    r"cfg scale": "diffusion sampler settings",
    r"dreamstudio": "DreamStudio",
    r"bing image creator": "Bing Image Creator",
}

C2PA_PATTERNS = [rb"c2pa", rb"jumbf", rb"contentauth", rb"cai:"]

# Phone / camera firmware strings that legitimately live in the Software tag.
FIRMWARE_PATTERNS = [
    r"^\d+(\.\d+)*$", r"^ios", r"^android", r"hdr\+", r"^ver\.?\s*\d", r"firmware", r"^v\d",
    r"samsung", r"google", r"pixel", r"oneplus", r"xiaomi", r"huawei", r"oppo", r"vivo", r"realme",
    r"motorola", r"nokia", r"sony", r"canon", r"nikon", r"fujifilm", r"olympus", r"panasonic",
    r"leica", r"hasselblad", r"gopro", r"dji", r"apple", r"^[a-z]\d{3,}", r"camera",
]

_INTERESTING_TAGS = [
    "Make", "Model", "Software", "DateTime", "DateTimeOriginal", "DateTimeDigitized", "Artist",
    "Copyright", "ImageDescription", "LensModel", "ExposureTime", "FNumber", "ISOSpeedRatings",
    "FocalLength", "Flash", "WhiteBalance", "ExifImageWidth", "ExifImageHeight", "Orientation",
    "ColorSpace", "HostComputer",
]


def _clean(v) -> str | int | float | None:
    try:
        if isinstance(v, bytes):
            s = v.decode("utf-8", "replace").strip("\x00 ").strip()
            return s[:200] if s and s.isprintable() else None
        if isinstance(v, (int, float)):
            return v
        if hasattr(v, "numerator") and hasattr(v, "denominator"):
            return round(float(v), 4) if v.denominator else None
        if isinstance(v, tuple):
            return ", ".join(str(_clean(x)) for x in v[:8])[:200]
        s = str(v).strip("\x00 ").strip()
        return s[:200] if s else None
    except Exception:
        return None


def extract_exif(exif) -> dict:
    out: dict = {}
    if not exif:
        return out
    try:
        items = dict(exif.items())
        try:
            items.update(exif.get_ifd(0x8769))  # Exif sub-IFD
        except Exception:
            pass
        has_gps = False
        try:
            has_gps = bool(exif.get_ifd(0x8825))
        except Exception:
            pass
        for tag_id, val in items.items():
            name = ExifTags.TAGS.get(tag_id)
            if name in _INTERESTING_TAGS:
                cv = _clean(val)
                if cv is not None and cv != "":
                    out[name] = cv
        if has_gps:
            out["GPS"] = "present"
    except Exception:
        pass
    return out


def _text_blobs(img) -> tuple[str, list[str]]:
    """Collect textual metadata (PNG tEXt/iTXt chunks, XMP, comments). Returns (joined text, keys)."""
    parts, keys = [], []
    for k, v in (img.info or {}).items():
        if k in ("exif", "icc_profile", "dpi", "gamma", "transparency", "duration", "loop",
                 "background", "chromaticity", "srgb", "jfif", "jfif_version", "jfif_unit",
                 "jfif_density", "progressive", "progression", "adobe", "adobe_transform"):
            continue
        keys.append(str(k))
        if isinstance(v, bytes):
            v = v[:20000].decode("utf-8", "replace")
        parts.append(f"{k}: {str(v)[:20000]}")
    return "\n".join(parts), keys


def analyze_metadata(img) -> dict:
    """`img` is a preprocessing.LoadedImage. Returns a signal dict plus extra fields."""
    exif = extract_exif(img.pil_exif)
    text, keys = _text_blobs(img)
    head_lower = img.head_bytes.lower()
    scan_text = (text + "\n" + " ".join(str(v) for v in exif.values())).lower()
    # Also scan raw container bytes (XMP packets, C2PA manifests, JPEG comments).
    raw_ascii = head_lower.decode("latin-1", "ignore")

    software = exif.get("Software")
    software_s = str(software).lower() if software else ""
    camera = bool(exif.get("Make") or exif.get("Model"))
    capture_detail = sum(1 for k in ("DateTimeOriginal", "ExposureTime", "FNumber", "ISOSpeedRatings",
                                     "FocalLength") if k in exif)

    ai_hits: list[str] = []
    for pat, name in AI_PATTERNS.items():
        if re.search(pat, scan_text) or re.search(pat, raw_ascii):
            if name not in ai_hits:
                ai_hits.append(name)
    # A1111 / ComfyUI write prompts into PNG chunks named "parameters", "prompt", "workflow".
    gen_keys = [k for k in keys if k.lower() in ("parameters", "prompt", "workflow", "invokeai_metadata",
                                                  "sd-metadata", "dream", "generation_data")]
    if gen_keys:
        ai_hits.append("generator chunk(s): " + ", ".join(gen_keys))
    # "imagen"/"gemini"/"openai" are short words that can appear in unrelated text - require context.
    weak = {"Google Imagen", "Google Gemini", "OpenAI"}
    strong_hits = [h for h in ai_hits if h not in weak]
    if not strong_hits and ai_hits and not (camera and capture_detail >= 2):
        strong_hits = ai_hits
    ai_hits = strong_hits

    c2pa = any(p in head_lower for p in C2PA_PATTERNS)

    # XMP CreatorTool / HistorySoftwareAgent name the program that last wrote the file.
    xmp_tools = " ".join(m.group(1) for m in re.finditer(
        r"(?:creatortool|softwareagent)\s*(?:=\s*\"|>)\s*([^\"<]{1,120})", raw_ascii))
    editor = None
    for pat in EDITOR_PATTERNS:
        m = re.search(pat, software_s) or re.search(pat, xmp_tools)
        if m:
            editor = m.group(0)
            break
    if software_s and editor is None:
        firmware = any(re.search(p, software_s) for p in FIRMWARE_PATTERNS)
    else:
        firmware = False

    lossless = img.format in ("PNG", "WEBP", "BMP", "TIFF", "GIF")
    findings: list[str] = []
    if ai_hits:
        score = SCORE_AI_HINT
        findings.append("metadata contains AI-generator fingerprints (" + "; ".join(ai_hits[:4]) + ")")
    elif editor:
        score = SCORE_EDITOR
        findings.append(f"the file was saved by editing software ({software or editor})")
    elif camera and capture_detail >= 2:
        score = SCORE_CAMERA_CLEAN
        findings.append(f"camera metadata present ({exif.get('Make', '')} {exif.get('Model', '')}".strip()
                        + ") with capture settings")
    elif camera:
        score = SCORE_PARTIAL
        findings.append("camera make/model present but most capture settings are missing")
    elif lossless:
        score = SCORE_NO_METADATA_LOSSLESS
        findings.append(f"no camera metadata (common for {img.format} screenshots, exports and web images)")
    else:
        score = SCORE_NO_CAMERA_JPEG
        findings.append("no camera metadata (often stripped by social media/messaging apps, or by editors)")
    if c2pa:
        findings.append("a C2PA / Content Credentials manifest appears to be embedded (provenance data present)")
    if software and not editor and not ai_hits:
        findings.append(f"software tag '{software}'" + (" looks like normal camera firmware" if firmware else ""))

    explanation = "Metadata: " + "; ".join(findings) + "."
    if not ai_hits and not editor:
        explanation += " Metadata alone cannot prove authenticity because it is easy to strip or edit."

    return {
        "key": "metadata",
        "label": "Metadata (EXIF) analysis",
        "score": float(score),
        "available": True,
        "explanation": explanation,
        "details": {
            "camera_present": camera,
            "capture_fields": capture_detail,
            "software": software,
            "editor_detected": editor,
            "ai_generator_hints": ai_hits,
            "c2pa_manifest": c2pa,
            "text_chunks": keys[:20],
            "jpeg_quality_estimate": img.jpeg_quality,
            "exif_tag_count": len(exif),
        },
        # extra, consumed by pipeline (not part of the signal dict sent out)
        "_exif": exif,
        "_software": software,
        "_ai_hint": bool(ai_hits),
        "_editor": editor,
    }
