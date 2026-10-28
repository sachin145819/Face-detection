"""Video analysis (docs/CONTRACT.md §6): probe + frame-sampled deepfake / AI-generated detection.

    probe_video(path) -> dict                         (ValueError if not a decodable video)
    analyze_video(path, output_dir, max_frames=None) -> dict

Frames are sampled evenly over the duration and run through the SAME detectors as the image pipeline
(YuNet faces -> SigLIP deepfake per face, SwinV2 AI-generated on the whole frame). Classical image
forensics (ELA / noise) are not used: video codecs destroy those traces. Per-frame results are
aggregated robustly (top-k mean blended with the median, so a few strong frames count but a single
outlier does not dominate), combined with a weak temporal-consistency cue and container metadata,
and fused into a verdict using the image decision engine's thresholds.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import shutil
import subprocess
import time
import warnings

import cv2
import numpy as np

from . import decision, explain
from .detectors import faces as face_det
from .detectors.ai_generated import analyze_ai_generated
from .detectors.deepfake import analyze_faces
from .utils import clamp01, deep_enabled, resize_max, to_py

log = logging.getLogger(__name__)

VIDEO_PIPELINE_VERSION = "truthlens-video-1.0"

# ---- sampling / output -------------------------------------------------------------------------
DEFAULT_MAX_FRAMES = 16
MAX_FRAMES_LIMIT = 64            # hard cap whatever the caller / env asks for
THUMB_MAX_SIDE = 640             # contract: thumbnails <= 640 px on the long side
THUMB_JPEG_QUALITY = 85
HEATMAP_MAX_SIDE = 960           # overlay images for the top frames
MAX_TOP_FRAMES = 4
SEQUENTIAL_READ_LIMIT = 20000    # safety cap for the decode-everything fallback
FFPROBE_TIMEOUT_S = 15
META_SCAN_BYTES = 2 * 1024 * 1024

# ---- fusion (thresholds shared with the image decision engine) ---------------------------------
VIDEO_WEIGHTS = {"deepfake": 0.40, "ai_generated": 0.35, "temporal": 0.10, "metadata": 0.15}
VIDEO_SIGNAL_ORDER = ["deepfake", "ai_generated", "temporal", "metadata"]
VIDEO_LABELS = {
    "deepfake": "Face deepfake (across frames)",
    "ai_generated": "AI-generated frames",
    "temporal": "Temporal consistency",
    "metadata": "Container metadata",
}
DEEPFAKE_THRESHOLD = decision.DEEPFAKE_THRESHOLD          # 0.70
AI_GENERATED_THRESHOLD = decision.AI_GENERATED_THRESHOLD  # 0.80
DEEPFAKE_BORDERLINE = decision.DEEPFAKE_BORDERLINE        # 0.45
AI_BORDERLINE = decision.AI_BORDERLINE                    # 0.50
STRONG_SIGNAL = decision.STRONG_SIGNAL                    # 0.60
FUSED_SUSPICION_THRESHOLD = decision.FUSED_SUSPICION_THRESHOLD
METADATA_AI_PROB = decision.METADATA_AI_PROB
AUTHENTIC_MIN_SCORE = decision.AUTHENTIC_MIN_SCORE
NON_AUTHENTIC_MAX_SCORE = decision.NON_AUTHENTIC_MAX_SCORE
MIN_SCORE = decision.MIN_SCORE
MAX_CONFIDENCE = decision.MAX_CONFIDENCE
# robust aggregation: agg = TOPK_BLEND * mean(top-k) + (1 - TOPK_BLEND) * median, k = ceil(TOPK_FRAC * n), k >= 2
DEEPFAKE_TOPK_BLEND = 0.75
AI_TOPK_BLEND = 0.60
TOPK_FRAC = 0.25
MIN_TOPK = 2
# Video face calibration. The face deepfake model was trained on large, clean still crops; on video frames
# (faces of 100-250 px, codec-compressed) it reads REAL faces as 0.8-0.97 "fake" (measured on public-domain
# interview clips). Its probability is therefore shrunk towards 0.5 ("don't know") by a trust factor
# that grows with face size: trust = clip((size - MIN_PX) / (FULL_TRUST_PX - MIN_PX), MIN_TRUST, 1).
VIDEO_FACE_MIN_PX = 64
VIDEO_FACE_FULL_TRUST_PX = 400
VIDEO_FACE_MIN_TRUST = 0.2
# Partially synthetic clips (spliced / edited): a run of >= SEGMENT_MIN_FRAMES consecutive sampled frames
# (and >= SEGMENT_MIN_FRAC of all samples) that each clear a per-frame bar raises the verdict even when the
# whole-video aggregate is diluted by the authentic part. The per-frame bars are stricter than the
# video-level thresholds so a couple of noisy frames can't trigger it.
SEGMENT_MIN_FRAMES = 3
SEGMENT_MIN_FRAC = 0.15
SEGMENT_AI_FRAME_MIN = 0.90
SEGMENT_DEEPFAKE_FRAME_MIN = 0.72   # calibrated face probability (real interview clips peaked at 0.68)
SEGMENT_GAP_MARGIN = 0.10
SEGMENT_CONFIDENCE_FACTOR = 0.90
# per-frame fused suspicion = FRAME_MAX_W * max(available probs) + (1 - FRAME_MAX_W) * mean(available probs)
FRAME_MAX_W = 0.8
# temporal cue: mean |change| between consecutive samples, normalised by this jump size
TEMPORAL_JUMP_NORM = 0.35
TEMPORAL_MIN_FRAMES = 3
# metadata signal scores
META_SCORE_GENERATOR = 0.95
META_SCORE_FACESWAP = 0.95
META_SCORE_COMPOSITE = 0.60
META_SCORE_EDITOR = 0.20
META_SCORE_CAMERA = 0.02
META_SCORE_NEUTRAL = 0.10
# quality limits for the uncertainty note
SHORT_VIDEO_S = 2.0
LOW_RES_MIN_SIDE = 360
HEAVY_COMPRESSION_BPP = 0.025    # bits per pixel per frame
FEW_FRAMES = 6

# ---- metadata patterns ---------------------------------------------------------------------------
AI_VIDEO_PATTERNS = {
    r"\bsora\b": "OpenAI Sora",
    r"openai": "OpenAI",
    r"runway\s?ml|\brunway\b": "Runway",
    r"\bgen-?[234](\s?alpha|\s?turbo)?\b": "Runway Gen-2/3/4",
    r"\bpika(\s?labs|\.art)?\b": "Pika",
    r"luma\s?(ai|labs)|dream\s?machine": "Luma Dream Machine",
    r"\bkling\b|kuaishou": "Kling",
    r"google\s?veo|\bveo\s?[123]\b|\bveo\b": "Google Veo",
    r"synthesia": "Synthesia",
    r"heygen": "HeyGen",
    r"\bd-id\b|studio\.d-id": "D-ID",
    r"stable[\s_-]?video[\s_-]?diffusion|\bsvd(_xt)?\b": "Stable Video Diffusion",
    r"animatediff": "AnimateDiff",
    r"hailuo|minimax": "Hailuo / MiniMax",
    r"haiper": "Haiper",
    r"invideo\s?ai": "InVideo AI",
    r"colossyan": "Colossyan",
    r"hunyuan\s?video": "HunyuanVideo",
    r"\bwan\s?2\.\d\b": "Wan",
    r"cogvideo": "CogVideo",
    r"ltx[\s-]?video": "LTX-Video",
    r"midjourney": "Midjourney",
    r"firefly": "Adobe Firefly",
    r"trainedalgorithmicmedia": "IPTC 'trained algorithmic media' (AI-generated) tag",
}
FACESWAP_PATTERNS = {
    r"deepfacelab": "DeepFaceLab",
    r"facefusion": "FaceFusion",
    r"\broop\b": "Roop",
    r"faceswap": "FaceSwap",
    r"deep[\s-]?live[\s-]?cam": "Deep-Live-Cam",
    r"simswap": "SimSwap",
    r"reface": "Reface",
    r"deepswap": "DeepSwap",
    r"swapface": "Swapface",
    r"wav2lip": "Wav2Lip (lip-sync)",
    r"liveportrait": "LivePortrait",
}
COMPOSITE_PATTERNS = {r"compositewithtrainedalgorithmicmedia": "IPTC 'composite with AI' tag"}
EDITOR_PATTERNS = {
    r"premiere": "Adobe Premiere", r"after\s?effects": "Adobe After Effects", r"davinci|resolve": "DaVinci Resolve",
    r"final\s?cut": "Final Cut Pro", r"imovie": "iMovie", r"capcut": "CapCut", r"filmora": "Filmora",
    r"vegas": "Vegas", r"kinemaster": "KineMaster", r"inshot": "InShot", r"shotcut": "Shotcut",
    r"openshot": "OpenShot", r"kdenlive": "Kdenlive", r"handbrake": "HandBrake", r"clipchamp": "Clipchamp",
}
CAMERA_TAG_RE = re.compile(r"com\.apple\.quicktime\.(make|model)|com\.android\.(version|capture)|"
                           r"samsung|^make$|^model$|location", re.I)
C2PA_RE = re.compile(rb"c2pa[._:][a-z]|jumd.{0,48}c2pa|contentauth|urn:c2pa", re.I | re.S)
TEXT_RUN_RE = re.compile(rb"[\x20-\x7e]{8,}")

_FOURCC_NAMES = {
    "avc1": "h264", "h264": "h264", "x264": "h264", "avc3": "h264", "hvc1": "hevc", "hev1": "hevc",
    "hevc": "hevc", "h265": "hevc", "mp4v": "mpeg4", "fmp4": "mpeg4", "xvid": "mpeg4", "divx": "mpeg4",
    "mjpg": "mjpeg", "mjpa": "mjpeg", "jpeg": "mjpeg", "vp80": "vp8", "vp8": "vp8", "vp90": "vp9",
    "vp9": "vp9", "av01": "av1", "ap4h": "prores", "apcn": "prores", "apch": "prores", "apcs": "prores",
    "mpg2": "mpeg2video", "mpg1": "mpeg1video", "wmv3": "wmv3", "theo": "theora",
}


# =================================================================================================
# probing
# =================================================================================================
def _ffprobe(path: str) -> dict | None:
    exe = shutil.which("ffprobe")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "-v", "error", "-show_format", "-show_streams", "-of", "json", path],
                             capture_output=True, timeout=FFPROBE_TIMEOUT_S, check=False)
        if out.returncode != 0 or not out.stdout:
            return None
        return json.loads(out.stdout.decode("utf-8", "replace"))
    except Exception as exc:  # timeout, bad JSON ...
        log.info("ffprobe failed on %s: %s", path, exc)
        return None


def _video_stream(ff: dict | None) -> dict | None:
    if not ff:
        return None
    for s in ff.get("streams") or []:
        if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic"):
            return s
    return None


def _fourcc_str(v: float) -> str | None:
    try:
        i = int(v)
    except (TypeError, ValueError):
        return None
    if i <= 0:
        return None
    s = "".join(chr((i >> (8 * k)) & 0xFF) for k in range(4))
    s = s.strip("\x00 ").lower()
    return s if s and all(32 <= ord(c) < 127 for c in s) else None


def _sniff_format(path: str) -> str | None:
    try:
        with open(path, "rb") as fh:
            head = fh.read(4096)
    except OSError:
        return None
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand == b"qt  ":
            return "mov"
        if brand.startswith(b"3gp") or brand.startswith(b"3g2"):
            return "3gp"
        return "mp4"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "webm" if b"webm" in head[:256] else "mkv"
    if head[:4] == b"RIFF" and head[8:12] == b"AVI ":
        return "avi"
    if head[:3] == b"FLV":
        return "flv"
    if head[:4] in (b"\x00\x00\x01\xba", b"\x00\x00\x01\xb3"):
        return "mpeg"
    if len(head) > 376 and head[0] == 0x47 and head[188] == 0x47:
        return "mpegts"
    if b"moov" in head[:64] or b"mdat" in head[:64]:
        return "mov"
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return ext or None


def _format_name(path: str, ff: dict | None) -> str | None:
    sniffed = _sniff_format(path)
    fmt = ((ff or {}).get("format") or {}).get("format_name")
    if fmt:
        names = fmt.split(",")
        if sniffed in names:
            return sniffed
        if "mov" in names and "mp4" in names:   # ffprobe reports mov,mp4,m4a,3gp,3g2,mj2 for all ISO-BMFF
            return sniffed if sniffed in ("mp4", "mov", "3gp") else "mp4"
        if "matroska" in names:
            return sniffed if sniffed in ("webm", "mkv") else "mkv"
        return names[0]
    return sniffed


def _float_or_none(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _rate(s: str | None) -> float | None:
    if not s or "/" not in str(s):
        return _float_or_none(s)
    a, b = str(s).split("/", 1)
    a, b = _float_or_none(a), _float_or_none(b)
    return a / b if a is not None and b else None


def _open(path: str) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(path, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        cap.release()
        cap = cv2.VideoCapture(path)   # let OpenCV pick another backend (e.g. AVFoundation / MJPEG)
    if cap.isOpened() and hasattr(cv2, "CAP_PROP_ORIENTATION_AUTO"):
        cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)   # frames come out in display orientation
    return cap


def _probe(path: str) -> tuple[dict, dict]:
    """Return (public probe dict, internal info). Raises ValueError if undecodable."""
    if not path or not os.path.isfile(path):
        raise ValueError("video file not found")
    if os.path.getsize(path) < 32:
        raise ValueError("file is too small to be a video")
    with open(path, "rb") as fh:
        magic = fh.read(16)
    if (magic.startswith(b"\xff\xd8\xff") or magic.startswith(b"\x89PNG") or magic[:4] == b"GIF8"
            or (magic[:4] == b"RIFF" and magic[8:12] == b"WEBP")):
        raise ValueError("this is a still image, not a video")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cap = _open(path)
        if not cap.isOpened():
            cap.release()
            raise ValueError("not a decodable video (could not open the container)")
        try:
            ok, frame = cap.read()
            if not ok or frame is None or frame.size == 0 or frame.ndim < 2:
                raise ValueError("not a decodable video (no frame could be decoded)")
            height, width = int(frame.shape[0]), int(frame.shape[1])
            fps = _float_or_none(cap.get(cv2.CAP_PROP_FPS))
            count = _float_or_none(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fourcc = _fourcc_str(cap.get(cv2.CAP_PROP_FOURCC))
            rotation = 0
            if hasattr(cv2, "CAP_PROP_ORIENTATION_META"):
                rotation = int(_float_or_none(cap.get(cv2.CAP_PROP_ORIENTATION_META)) or 0)
        finally:
            cap.release()

    ff = _ffprobe(path)
    vs = _video_stream(ff)
    fps_ok = fps is not None and 0.5 <= fps <= 240.0
    count_ok = count is not None and 1 <= count < 5e7
    ff_dur = None
    if ff:
        ff_dur = _float_or_none((ff.get("format") or {}).get("duration"))
        if vs is not None and _float_or_none(vs.get("duration")):
            ff_dur = _float_or_none(vs.get("duration"))
        if vs is not None and not fps_ok:
            r = _rate(vs.get("avg_frame_rate")) or _rate(vs.get("r_frame_rate"))
            if r and 0.5 <= r <= 240.0:
                fps, fps_ok = r, True
        if vs is not None and not count_ok:
            nb = _float_or_none(vs.get("nb_frames"))
            if nb and nb >= 1:
                count, count_ok = nb, True
    if ff_dur is not None and ff_dur <= 0:
        ff_dur = None

    counted = False
    if not count_ok and fps_ok and ff_dur:
        count, count_ok = round(ff_dur * fps), True
    duration = None
    if not count_ok or not fps_ok:
        # Metadata missing/bogus (typical for some WebM/MKV): decode once to count frames + last timestamp.
        n, last_ms = _count_frames(path)
        if n >= 1:
            counted = True
            count, count_ok = float(n), True
            if last_ms and last_ms > 0 and n > 1:
                duration = (last_ms / 1000.0) * n / (n - 1)   # last pts + one frame
                if not fps_ok:
                    fps, fps_ok = (n / duration if duration > 0 else None), duration > 0
            if not fps_ok:
                fps, fps_ok = 25.0, False   # unknown: assume a common rate
    count_i = int(round(count)) if count_ok else 1
    if duration is None:
        if fps_ok and fps:
            duration = count_i / fps
        elif ff_dur:
            duration = ff_dur
        else:
            duration = 0.0
    if ff_dur and fps_ok and not counted and abs(ff_dur - duration) > max(1.0, 0.25 * ff_dur):
        duration = ff_dur  # container duration is more trustworthy than a bogus frame count

    codec = (vs or {}).get("codec_name") or (_FOURCC_NAMES.get(fourcc, fourcc) if fourcc else None)
    if vs is not None:
        try:
            rot_tag = int(float((vs.get("tags") or {}).get("rotate", 0)))
        except (TypeError, ValueError):
            rot_tag = 0
        for sd in vs.get("side_data_list") or []:
            if "rotation" in sd:
                rot_tag = rot_tag or int(_float_or_none(sd.get("rotation")) or 0)
        rotation = rotation or rot_tag
    public = {
        "duration_s": round(float(duration), 3),
        "fps": round(float(fps or 0.0), 3),
        "frame_count": int(count_i),
        "width": width,
        "height": height,
        "codec": codec,
        "format": _format_name(path, ff),
    }
    internal = {"ffprobe": ff, "fps_reliable": bool(fps_ok), "count_reliable": bool(count_ok),
                "counted": counted, "rotation": int(rotation) % 360, "fourcc": fourcc,
                "file_size": os.path.getsize(path)}
    return public, internal


def _count_frames(path: str) -> tuple[int, float]:
    cap = _open(path)
    n, last_ms = 0, 0.0
    try:
        while n < SEQUENTIAL_READ_LIMIT and cap.grab():
            n += 1
            ms = _float_or_none(cap.get(cv2.CAP_PROP_POS_MSEC))
            if ms is not None and ms > last_ms:
                last_ms = ms
    finally:
        cap.release()
    return n, last_ms


def probe_video(video_path: str) -> dict:
    public, _ = _probe(video_path)
    return to_py(public)


# =================================================================================================
# frame sampling
# =================================================================================================
def _max_frames(max_frames: int | None) -> int:
    if max_frames is None:
        try:
            max_frames = int(os.environ.get("VIDEO_MAX_FRAMES", DEFAULT_MAX_FRAMES))
        except ValueError:
            max_frames = DEFAULT_MAX_FRAMES
    return int(max(1, min(MAX_FRAMES_LIMIT, max_frames)))


def _sample_targets(info: dict, n: int) -> list[tuple[int, float]]:
    """Evenly spaced (frame_index, timestamp_s) targets at the centres of n equal time slices."""
    count = max(1, int(info["frame_count"]))
    fps = float(info["fps"]) or 25.0
    n = min(n, count)
    out, seen = [], set()
    for i in range(n):
        idx = min(count - 1, int((i + 0.5) * count / n))
        if idx in seen:
            continue
        seen.add(idx)
        out.append((idx, idx / fps))
    return out


def _fit(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    if frame.ndim == 2:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    elif frame.shape[2] == 4:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    if frame.shape[1] != width or frame.shape[0] != height:   # mid-stream resolution change
        frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
    return frame


def _read_frames(path: str, info: dict, targets: list[tuple[int, float]]):
    """Yield (frame_index, timestamp_s, bgr). Seeks by frame index; if seeking misbehaves, falls back
    to decoding sequentially. Returns via generator; the mode used is stored in info['_sampling']."""
    w, h = info["width"], info["height"]
    fps = float(info["fps"]) or 25.0
    got: list[tuple[int, float, np.ndarray]] = []
    cap = _open(path)
    mode = "seek"
    try:
        for idx, t in targets:
            ok = cap.set(cv2.CAP_PROP_POS_FRAMES, float(idx))
            ok2, frame = cap.read() if ok else (False, None)
            if not ok2 or frame is None:
                # retry once by timestamp before giving up on seeking
                cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
                ok2, frame = cap.read()
                if not ok2 or frame is None:
                    mode = "sequential"
                    break
            ms = _float_or_none(cap.get(cv2.CAP_PROP_POS_MSEC))
            ts = ms / 1000.0 if (ms is not None and ms >= 0 and not info.get("_fps_unreliable")) else t
            if ts <= 0 and idx > 0:
                ts = t
            got.append((idx, float(ts), _fit(frame, w, h)))
    finally:
        cap.release()
    if mode == "seek" and got:
        # sanity: timestamps must be increasing, otherwise the demuxer ignored our seeks
        tss = [g[1] for g in got]
        if len(tss) >= 3 and len(set(round(x, 3) for x in tss)) < max(2, len(tss) // 2):
            mode, got = "sequential", []
    if mode == "sequential" or not got:
        mode = "sequential"
        got = []
        want = {idx: t for idx, t in targets}
        cap = _open(path)
        try:
            i = 0
            last = max(want) if want else 0
            while i <= last and i < SEQUENTIAL_READ_LIMIT and cap.grab():
                if i in want:
                    ok, frame = cap.retrieve()
                    if ok and frame is not None:
                        got.append((i, i / fps, _fit(frame, w, h)))
                i += 1
        finally:
            cap.release()
        if not got:   # frame count was wrong: take whatever the first frame is
            cap = _open(path)
            try:
                ok, frame = cap.read()
                if ok and frame is not None:
                    got.append((0, 0.0, _fit(frame, w, h)))
            finally:
                cap.release()
    info["_sampling"] = mode
    return got


# =================================================================================================
# metadata
# =================================================================================================
def _match(patterns: dict, text: str) -> list[str]:
    hits = []
    for pat, name in patterns.items():
        if re.search(pat, text, re.I) and name not in hits:
            hits.append(name)
    return hits


def _textual(run: bytes) -> bool:
    letters = sum(1 for c in run if (65 <= c <= 90) or (97 <= c <= 122) or c == 32)
    return letters >= 0.7 * len(run)


def _analyze_metadata(path: str, ff: dict | None) -> tuple[dict, dict]:
    """Returns (signal, public metadata dict)."""
    tags: dict = {}
    encoder = None
    camera = False
    if ff:
        fmt_tags = (ff.get("format") or {}).get("tags") or {}
        for k, v in fmt_tags.items():
            tags[str(k)[:64]] = str(v)[:200]
        for s in ff.get("streams") or []:
            for k, v in (s.get("tags") or {}).items():
                key = f"{s.get('codec_type', 'stream')}:{k}"[:64]
                if key not in tags and len(tags) < 60:
                    tags[key] = str(v)[:200]
        encoder = fmt_tags.get("encoder") or fmt_tags.get("ENCODER") or fmt_tags.get("com.apple.quicktime.software")
        vs = _video_stream(ff)
        if not encoder and vs is not None:
            encoder = (vs.get("tags") or {}).get("encoder")
        camera = any(CAMERA_TAG_RE.search(k) for k in fmt_tags)
    tag_text = " ".join(f"{k}={v}" for k, v in tags.items())

    # byte scan of the head and tail (XMP / C2PA / udta atoms often live there); textual runs only so
    # that short names (Veo, Pika, Roop) can't match random compressed bytes.
    head = tail = b""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            head = fh.read(META_SCAN_BYTES)
            if size > META_SCAN_BYTES:
                fh.seek(max(META_SCAN_BYTES, size - META_SCAN_BYTES))
                tail = fh.read(META_SCAN_BYTES)
    except OSError:
        pass
    raw = head + b"\n" + tail
    runs = [m.group(0) for m in TEXT_RUN_RE.finditer(raw)]
    scan_text = " ".join(r.decode("ascii", "ignore") for r in runs if _textual(r))[:200000]
    c2pa = bool(C2PA_RE.search(raw))
    if not encoder:
        m = re.search(r"(Lavf[\d.]+|x264 - core \d+|x265|HandBrake[\w .-]*)", scan_text)
        encoder = m.group(1) if m else None
    if not camera:
        camera = bool(re.search(r"com\.apple\.quicktime\.(make|model)|com\.android\.version", scan_text))

    text = tag_text + " " + scan_text
    gen = _match(AI_VIDEO_PATTERNS, tag_text)
    gen += [h for h in _match(AI_VIDEO_PATTERNS, scan_text) if h not in gen]
    swap = _match(FACESWAP_PATTERNS, text)
    composite = _match(COMPOSITE_PATTERNS, text.lower())
    if composite:   # "compositeWith..." also contains "trainedAlgorithmicMedia": don't count it twice
        gen = [g for g in gen if not g.startswith("IPTC 'trained")]
    editors = _match(EDITOR_PATTERNS, tag_text + " " + (encoder or ""))

    findings = []
    if gen:
        score = META_SCORE_GENERATOR
        findings.append("the file's metadata names an AI video generator (" + ", ".join(gen[:3]) + ")")
    elif swap:
        score = META_SCORE_FACESWAP
        findings.append("the file's metadata names face-swap software (" + ", ".join(swap[:3]) + ")")
    elif composite:
        score = META_SCORE_COMPOSITE
        findings.append("a provenance tag says the video was composited with AI-generated content")
    elif editors:
        score = META_SCORE_EDITOR
        findings.append(f"the video was exported by editing software ({editors[0]}); this is often harmless")
    elif camera:
        score = META_SCORE_CAMERA
        findings.append("phone/camera recording tags are present")
    else:
        score = META_SCORE_NEUTRAL
        findings.append("no camera, editor or AI-generator tags were found (common after re-encoding or sharing)")
    if c2pa:
        findings.append("a C2PA / Content Credentials manifest appears to be embedded")
    if encoder and not editors:
        findings.append(f"encoder: {encoder}")
    expl = "Container metadata: " + "; ".join(findings) + "."
    hint = gen[0] if gen else (swap[0] if swap else None)
    signal = {
        "key": "metadata", "label": VIDEO_LABELS["metadata"], "score": score, "available": True,
        "explanation": expl[0].upper() + expl[1:],
        "details": {"encoder": encoder, "generator_hints": gen, "faceswap_hints": swap,
                    "composite_hint": bool(composite), "editor": editors[0] if editors else None,
                    "camera_tags": camera, "c2pa_manifest": c2pa, "ffprobe": ff is not None},
        "_gen": bool(gen), "_swap": bool(swap), "_composite": bool(composite),
    }
    public = {"encoder": encoder, "generator_hint": hint, "tags": tags}
    return signal, public


# =================================================================================================
# aggregation helpers
# =================================================================================================
def robust_aggregate(values: list[float], blend: float) -> float:
    """blend * mean(top-k) + (1 - blend) * median with k = max(MIN_TOPK, ceil(TOPK_FRAC * n))."""
    v = sorted((float(x) for x in values), reverse=True)
    if not v:
        return 0.0
    if len(v) == 1:
        return v[0]
    k = min(len(v), max(MIN_TOPK, math.ceil(TOPK_FRAC * len(v))))
    return clamp01(blend * float(np.mean(v[:k])) + (1.0 - blend) * float(np.median(v)))


def face_trust(size_px: float) -> float:
    t = (float(size_px) - VIDEO_FACE_MIN_PX) / float(VIDEO_FACE_FULL_TRUST_PX - VIDEO_FACE_MIN_PX)
    return float(min(1.0, max(VIDEO_FACE_MIN_TRUST, t)))


def calibrate_face_probability(p: float, size_px: float) -> float:
    """Shrink a per-face deepfake probability towards 0.5 for small (less trustworthy) video faces."""
    return clamp01(0.5 + (float(p) - 0.5) * face_trust(size_px))


def frame_suspicion(df: float | None, ai: float | None) -> float:
    vals = [x for x in (df, ai) if x is not None]
    if not vals:
        return 0.0
    return clamp01(FRAME_MAX_W * max(vals) + (1.0 - FRAME_MAX_W) * float(np.mean(vals)))


def find_segment(frames: list[dict], key: str, frame_min: float) -> dict | None:
    """Longest run of consecutive sampled frames whose `key` value is >= frame_min. One interior frame that
    dips at most SEGMENT_GAP_MARGIN below the bar is tolerated (None always breaks a run). The run must
    also average >= frame_min and cover >= max(SEGMENT_MIN_FRAMES, SEGMENT_MIN_FRAC * n) samples."""
    n = len(frames)
    vals = [f.get(key) for f in frames]
    best = None
    start = 0
    while start < n:
        if vals[start] is None or vals[start] < frame_min:
            start += 1
            continue
        end, gap_used, i = start, False, start + 1
        while i < n and vals[i] is not None:
            if vals[i] >= frame_min:
                end = i
            elif not gap_used and vals[i] >= frame_min - SEGMENT_GAP_MARGIN:
                gap_used = True
            else:
                break
            i += 1
            if gap_used and end < i - 2:   # the tolerated dip must be followed by a strong frame
                break
        run = vals[start:end + 1]
        cand = {"start_index": start, "end_index": end, "frames": len(run),
                "start_s": frames[start]["timestamp_s"], "end_s": frames[end]["timestamp_s"],
                "mean": round(float(np.mean(run)), 4)}
        if cand["mean"] >= frame_min and (best is None or (cand["frames"], cand["mean"]) > (best["frames"], best["mean"])):
            best = cand
        start = end + 1
    if best is None or best["frames"] < max(SEGMENT_MIN_FRAMES, math.ceil(SEGMENT_MIN_FRAC * n)):
        return None
    best["partial"] = best["frames"] < n
    return best


def _mean_abs_diff(series: list[float]) -> float | None:
    if len(series) < 2:
        return None
    return float(np.mean(np.abs(np.diff(np.asarray(series, np.float64)))))


def _temporal_signal(frames: list[dict], deep_ok: bool) -> dict:
    n = len(frames)
    if not deep_ok or n < TEMPORAL_MIN_FRAMES:
        why = ("Too few frames could be sampled to compare them over time." if deep_ok else
               "The per-frame detectors were not available, so frame-to-frame consistency could not be measured.")
        return {"key": "temporal", "label": VIDEO_LABELS["temporal"], "score": 0.0, "available": False,
                "explanation": why, "details": {"frames": n}}
    df_series = [f["deepfake_probability"] for f in frames if f["deepfake_probability"] is not None]
    ai_series = [f["ai_generated_probability"] for f in frames if f["ai_generated_probability"] is not None]
    presence = [1 if f["faces"] else 0 for f in frames]
    j_df = _mean_abs_diff(df_series)
    j_ai = _mean_abs_diff(ai_series)
    flips = sum(1 for a, b in zip(presence, presence[1:]) if a != b) / max(1, n - 1)
    parts, wsum = 0.0, 0.0
    if j_df is not None:
        parts += 0.5 * clamp01(j_df / TEMPORAL_JUMP_NORM)
        wsum += 0.5
    if j_ai is not None:
        parts += 0.3 * clamp01(j_ai / TEMPORAL_JUMP_NORM)
        wsum += 0.3
    parts += 0.2 * flips
    wsum += 0.2
    score = clamp01(parts / wsum)
    if score >= STRONG_SIGNAL:
        expl = ("The detectors' readings jump a lot between neighbouring frames (and/or faces keep appearing and "
                "disappearing). Edited or generated clips can flicker like this, but so can scene cuts and fast "
                "motion, so this is only a weak hint.")
    elif score >= 0.3:
        expl = ("Readings vary somewhat from frame to frame; this is common in real footage with motion or cuts "
                "and is only a weak hint.")
    else:
        expl = "The per-frame readings are stable over time, as expected for an unedited continuous recording."
    return {"key": "temporal", "label": VIDEO_LABELS["temporal"], "score": score, "available": True,
            "explanation": expl,
            "details": {"deepfake_jump": None if j_df is None else round(j_df, 4),
                        "ai_jump": None if j_ai is None else round(j_ai, 4),
                        "face_presence_change_rate": round(flips, 4), "frames": n}}


# =================================================================================================
# main entry
# =================================================================================================
def _scaled_faces(faces_out: list[dict], s: float) -> list[dict]:
    out = []
    for f in faces_out:
        g = {"box": [v * s for v in f["box"]], "deepfake_probability": f.get("deepfake_probability")}
        if f.get("_cam") is not None:
            g["_cam"] = f["_cam"]
        if f.get("_crop_box") is not None:
            g["_crop_box"] = [v * s for v in f["_crop_box"]]
        out.append(g)
    return out


def analyze_video(video_path: str, output_dir: str, max_frames: int | None = None) -> dict:
    t0 = time.perf_counter()
    info, internal = _probe(video_path)   # ValueError if undecodable
    os.makedirs(output_dir, exist_ok=True)
    n_req = _max_frames(max_frames)
    deep = deep_enabled()
    W, H = info["width"], info["height"]

    work = dict(info)
    work["_fps_unreliable"] = not internal["fps_reliable"]
    targets = _sample_targets(work, n_req)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw_frames = _read_frames(video_path, work, targets)
    if not raw_frames:
        raise ValueError("not a decodable video (no frames could be read)")

    frames: list[dict] = []
    keep: list[dict] = []          # per-frame internals for heatmaps (downscaled image + CAMs)
    df_status = {"model_error": None, "too_small": 0, "failed": 0}
    ai_status = {"available": False, "error": None}
    detector_used = "none"
    for pos, (fidx, ts, bgr) in enumerate(raw_frames):
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        try:
            faces, detector_used = face_det.detect_faces(rgb)
        except Exception as exc:
            log.warning("face detection failed on frame %d: %s", fidx, exc)
            faces = []
        faces_out = [{"box": f["box"], "deepfake_probability": None, "analyzed": False} for f in faces]
        if faces:
            try:
                df_sig, faces_out = analyze_faces(rgb, faces, detector_used)
                if not df_sig.get("available"):
                    err = (df_sig.get("details") or {}).get("error")
                    if err or not deep:
                        df_status["model_error"] = err or "disabled"
                    elif "too small" in df_sig.get("explanation", ""):
                        df_status["too_small"] += 1
            except Exception as exc:
                log.exception("deepfake analysis failed on frame %d", fidx)
                df_status["failed"] += 1
        ai_p, ai_cam = None, None
        if deep:
            try:
                ai_sig, ai_cam = analyze_ai_generated(rgb)
                if ai_sig.get("available"):
                    ai_p = float(ai_sig["score"])
                    ai_status["available"] = True
                else:
                    ai_status["error"] = (ai_sig.get("details") or {}).get("error") or ai_sig.get("explanation")
            except Exception as exc:
                log.exception("AI-generated analysis failed on frame %d", fidx)
                ai_status["error"] = str(exc)[:200]
        for f in faces_out:
            if f.get("analyzed") and f.get("deepfake_probability") is not None:
                f["model_probability"] = float(f["deepfake_probability"])
                f["deepfake_probability"] = calibrate_face_probability(f["model_probability"],
                                                                       min(f["box"][2], f["box"][3]))
        analysed = [f for f in faces_out if f.get("analyzed") and f.get("deepfake_probability") is not None]
        df_p = max(float(f["deepfake_probability"]) for f in analysed) if analysed else None

        thumb, _ = resize_max(bgr, THUMB_MAX_SIDE)
        thumb_path = os.path.abspath(os.path.join(output_dir, f"frame_{pos:03d}.jpg"))
        cv2.imwrite(thumb_path, thumb, [cv2.IMWRITE_JPEG_QUALITY, THUMB_JPEG_QUALITY])
        small, s = resize_max(rgb, HEATMAP_MAX_SIDE)
        keep.append({"rgb": small, "scale": s, "faces": _scaled_faces(faces_out, s), "ai_cam": ai_cam})

        frames.append({
            "index": pos,
            "frame_number": int(fidx),
            "timestamp_s": round(float(ts), 3),
            "suspicion": round(frame_suspicion(df_p, ai_p), 4),
            "deepfake_probability": None if df_p is None else round(df_p, 4),
            "ai_generated_probability": None if ai_p is None else round(ai_p, 4),
            "faces": [{"box": [int(v) for v in f["box"]],
                       "deepfake_probability": (None if f.get("deepfake_probability") is None
                                                else round(float(f["deepfake_probability"]), 4)),
                       "model_probability": (None if f.get("model_probability") is None
                                             else round(float(f["model_probability"]), 4)),
                       "analyzed": bool(f.get("analyzed"))} for f in faces_out],
            "thumbnail_path": thumb_path if os.path.isfile(thumb_path) else None,
            "heatmap_path": None,
        })
        del rgb, bgr
    del raw_frames

    # ---------------- signals ----------------
    n = len(frames)
    face_frames = [f for f in frames if f["faces"]]
    df_frames = [f for f in frames if f["deepfake_probability"] is not None]
    ai_frames = [f for f in frames if f["ai_generated_probability"] is not None]

    model_versions = {"deepfake": None, "ai_generated": None}
    model_errors = {}
    if deep:
        from .detectors.models import get_model
        for k in ("deepfake", "ai_generated"):
            m = get_model(k)
            model_versions[k] = m.id if m.available else None
            if m.error:
                model_errors[k] = m.error

    face_sizes = [min(fc["box"][2], fc["box"][3]) for f in frames for fc in f["faces"] if fc["analyzed"]]
    median_face_px = float(np.median(face_sizes)) if face_sizes else None
    if df_frames:
        vals = [f["deepfake_probability"] for f in df_frames]
        raw_vals = [max(fc["model_probability"] for fc in f["faces"] if fc["model_probability"] is not None)
                    for f in df_frames]
        df_agg = robust_aggregate(vals, DEEPFAKE_TOPK_BLEND)
        above = sum(1 for v in vals if v >= DEEPFAKE_THRESHOLD)
        frac_above = above / len(vals)
        m = len(df_frames)
        if df_agg >= DEEPFAKE_THRESHOLD:
            expl = (f"Faces look synthetic or swapped in {above} of {m} analysed frames "
                    f"(aggregate {df_agg * 100:.0f}% deepfake probability).")
        elif df_agg >= DEEPFAKE_BORDERLINE:
            expl = (f"The face-forensics model is unsure across the video (aggregate {df_agg * 100:.0f}%; "
                    f"{above} of {m} frames above {DEEPFAKE_THRESHOLD * 100:.0f}%).")
        else:
            expl = (f"Faces were analysed in {m} frame{'s' if m != 1 else ''}; they look like real faces "
                    f"(aggregate {df_agg * 100:.0f}% deepfake probability).")
        df_sig = {"key": "deepfake", "label": VIDEO_LABELS["deepfake"], "score": df_agg, "available": True,
                  "explanation": expl,
                  "details": {"frames_with_faces": len(face_frames), "frames_analyzed": m,
                              "frames_above_threshold": above, "max": round(max(vals), 4),
                              "median": round(float(np.median(vals)), 4),
                              "raw_model_max": round(max(raw_vals), 4),
                              "median_face_px": None if median_face_px is None else round(median_face_px, 1),
                              "face_trust": None if median_face_px is None else round(face_trust(median_face_px), 3),
                              "aggregation": f"{DEEPFAKE_TOPK_BLEND:.2f}*mean(top-k)+{1 - DEEPFAKE_TOPK_BLEND:.2f}*median",
                              "model": model_versions["deepfake"]}}
    else:
        frac_above = 0.0
        if not face_frames:
            expl = "No faces were found in the sampled frames, so the face-deepfake check does not apply."
        elif not deep:
            expl = ("Deep-learning models are disabled on this server (ML_ENABLE_DEEP=false); faces were located "
                    "but not checked for deepfakes.")
        elif df_status["model_error"]:
            expl = "The deepfake model is not available on this server, so the detected faces were not checked."
        else:
            expl = "Faces were found but they were too small to analyse reliably for deepfakes."
        df_sig = {"key": "deepfake", "label": VIDEO_LABELS["deepfake"], "score": 0.0, "available": False,
                  "explanation": expl, "details": {"frames_with_faces": len(face_frames), "frames_analyzed": 0}}

    if ai_frames:
        vals = [f["ai_generated_probability"] for f in ai_frames]
        ai_agg = robust_aggregate(vals, AI_TOPK_BLEND)
        if ai_agg >= AI_GENERATED_THRESHOLD:
            expl = (f"The AI-image detector finds generator fingerprints throughout the video "
                    f"(aggregate {ai_agg * 100:.0f}% over {len(vals)} frames).")
        elif ai_agg >= AI_BORDERLINE:
            expl = (f"The AI-image detector leans towards AI generation (aggregate {ai_agg * 100:.0f}%), "
                    "but not decisively.")
        else:
            expl = (f"The frames look camera-recorded to the AI-image detector "
                    f"(aggregate {ai_agg * 100:.0f}% AI probability over {len(vals)} frames).")
        ai_sig = {"key": "ai_generated", "label": VIDEO_LABELS["ai_generated"], "score": ai_agg, "available": True,
                  "explanation": expl,
                  "details": {"frames_analyzed": len(vals), "max": round(max(vals), 4),
                              "median": round(float(np.median(vals)), 4),
                              "aggregation": f"{AI_TOPK_BLEND:.2f}*mean(top-k)+{1 - AI_TOPK_BLEND:.2f}*median",
                              "model": model_versions["ai_generated"]}}
    else:
        expl = ("Deep-learning models are disabled on this server (ML_ENABLE_DEEP=false)." if not deep else
                "The AI-image model is not available on this server (offline or not downloaded).")
        ai_sig = {"key": "ai_generated", "label": VIDEO_LABELS["ai_generated"], "score": 0.0, "available": False,
                  "explanation": expl, "details": {"error": ai_status["error"]} if ai_status["error"] else {}}

    seg_ai = find_segment(frames, "ai_generated_probability", SEGMENT_AI_FRAME_MIN)
    seg_df = find_segment(frames, "deepfake_probability", SEGMENT_DEEPFAKE_FRAME_MIN)
    if seg_ai:
        ai_sig["details"]["segment"] = seg_ai
    if seg_df:
        df_sig["details"]["segment"] = seg_df
    temporal = _temporal_signal(frames, bool(df_frames or ai_frames))
    try:
        meta_sig, meta_public = _analyze_metadata(video_path, internal["ffprobe"])
    except Exception as exc:
        log.exception("video metadata analysis failed")
        meta_sig = {"key": "metadata", "label": VIDEO_LABELS["metadata"], "score": 0.0, "available": False,
                    "explanation": f"Metadata could not be read ({type(exc).__name__}).", "details": {}}
        meta_public = {"encoder": None, "generator_hint": None, "tags": {}}

    signals = {"deepfake": df_sig, "ai_generated": ai_sig, "temporal": temporal, "metadata": meta_sig}
    ctx = {
        "deep": deep, "frames": n, "frames_requested": n_req, "face_frames": len(face_frames),
        "df_frames": len(df_frames), "frac_above": frac_above, "model_errors": model_errors,
        "duration": info["duration_s"], "min_side": min(W, H), "file_size": internal["file_size"],
        "fps": info["fps"], "width": W, "height": H, "too_small": df_status["too_small"],
        "median_face_px": median_face_px, "seg_ai": seg_ai, "seg_df": seg_df,
    }
    dec = _decide(signals, ctx)

    # ---------------- top frames + overlays ----------------
    order = sorted(range(n), key=lambda i: (-frames[i]["suspicion"], i))
    top = order[:min(MAX_TOP_FRAMES, n)]
    for i in top:
        k = keep[i]
        h, w = k["rgb"].shape[:2]
        ai_p = frames[i]["ai_generated_probability"]
        path = os.path.abspath(os.path.join(output_dir, f"frame_{i:03d}_heat.jpg"))
        try:
            sus, _ = explain.build_suspicion_map(w, h, None, None, k["faces"], ai_p, k["ai_cam"], {})
            regions = explain.merge_regions(explain.cam_regions(w, h, k["faces"], ai_p, k["ai_cam"]), w, h)
            explain.render_heatmap(k["rgb"], sus, regions, k["faces"], path)
            if os.path.isfile(path):
                frames[i]["heatmap_path"] = path
        except Exception:
            log.exception("video heatmap rendering failed for frame %d", i)
    del keep

    out_signals = []
    for key in VIDEO_SIGNAL_ORDER:
        s = signals[key]
        out_signals.append({
            "key": key, "label": s.get("label") or VIDEO_LABELS[key],
            "score": round(float(s.get("score") or 0.0), 4), "weight": dec["weights"][key],
            "available": bool(s.get("available")), "explanation": s.get("explanation") or "",
            "details": s.get("details") or {},
        })

    result = {
        "media_type": "video",
        "verdict": dec["verdict"],
        "authenticity_score": dec["authenticity_score"],
        "confidence": dec["confidence"],
        "summary": dec["summary"],
        "uncertainty_note": dec["uncertainty_note"],
        "signals": out_signals,
        "video": dict(info),
        "frames": frames,
        "top_frames": top,
        "faces_detected_frames": len(face_frames),
        "metadata": meta_public,
        "processing_ms": 0,
        "model_versions": model_versions,
        "partial_segment": dec["partial_segment"],
        "fusion": {"fused_suspicion": dec["fused_suspicion"], "pipeline_version": VIDEO_PIPELINE_VERSION,
                   "deep_enabled": deep, "frames_requested": n_req, "frames_analyzed": n,
                   "sampling": work.get("_sampling"), "face_detector": detector_used,
                   "rotation": internal["rotation"]},
    }
    result["processing_ms"] = int(round((time.perf_counter() - t0) * 1000))
    return to_py(result)


# =================================================================================================
# decision
# =================================================================================================
def _decide(signals: dict, ctx: dict) -> dict:
    avail = {k: bool(signals[k].get("available")) for k in VIDEO_SIGNAL_ORDER}
    scores = {k: float(signals[k].get("score") or 0.0) for k in VIDEO_SIGNAL_ORDER}
    total_w = sum(VIDEO_WEIGHTS[k] for k in VIDEO_SIGNAL_ORDER if avail[k])
    eff_w = {k: (VIDEO_WEIGHTS[k] / total_w if avail[k] and total_w > 0 else 0.0) for k in VIDEO_SIGNAL_ORDER}
    fused = sum(eff_w[k] * scores[k] for k in VIDEO_SIGNAL_ORDER)
    meta = signals["metadata"]
    meta_gen, meta_swap, meta_comp = bool(meta.get("_gen")), bool(meta.get("_swap")), bool(meta.get("_composite"))

    df = scores["deepfake"] if avail["deepfake"] else None
    ai = scores["ai_generated"] if avail["ai_generated"] else None
    candidates = []
    df_p = max(df or 0.0, METADATA_AI_PROB if meta_swap else 0.0)
    if (df is not None and df >= DEEPFAKE_THRESHOLD) or meta_swap:
        candidates.append(("deepfake", df_p))
    ai_p = max(ai or 0.0, METADATA_AI_PROB if meta_gen else 0.0)
    if (ai is not None and ai >= AI_GENERATED_THRESHOLD) or meta_gen:
        candidates.append(("ai_generated", ai_p))
    # partially synthetic clip: a confident run of frames that the whole-video aggregate dilutes
    partial = None
    seg_df, seg_ai = ctx.get("seg_df"), ctx.get("seg_ai")
    if seg_df and not any(c[0] == "deepfake" for c in candidates):
        candidates.append(("deepfake", seg_df["mean"]))
        partial = partial or {}
        partial["deepfake"] = seg_df
    if seg_ai and not any(c[0] == "ai_generated" for c in candidates):
        candidates.append(("ai_generated", seg_ai["mean"]))
        partial = partial or {}
        partial["ai_generated"] = seg_ai
    if candidates:
        candidates.sort(key=lambda c: (c[1], c[0] == "ai_generated"), reverse=True)
        verdict, p = candidates[0]
    elif fused >= FUSED_SUSPICION_THRESHOLD and (meta_comp or (avail["temporal"] and scores["temporal"] >= STRONG_SIGNAL)):
        verdict, p = "manipulated", fused
    else:
        verdict, p = "authentic", 1.0 - fused

    if verdict == "authentic":
        frac = clamp01(fused / FUSED_SUSPICION_THRESHOLD)
        score = 100.0 - frac * (100.0 - AUTHENTIC_MIN_SCORE)
    else:
        score = max(MIN_SCORE, min(100.0 * (1.0 - fused), NON_AUTHENTIC_MAX_SCORE, 100.0 * (1.0 - p) + 5.0))

    applicable = [k for k in VIDEO_SIGNAL_ORDER if not (k == "deepfake" and ctx["face_frames"] == 0)]
    cov = sum(VIDEO_WEIGHTS[k] for k in applicable if avail[k]) / max(1e-9, sum(VIDEO_WEIGHTS[k] for k in applicable))
    frame_cov = 0.7 + 0.3 * min(1.0, ctx["frames"] / 8.0)
    if verdict == "authentic":
        peak = max([scores[k] for k in ("deepfake", "ai_generated") if avail[k]] or [0.0])
        conf = (1.0 - 0.5 * fused - 0.5 * peak) * (0.4 + 0.6 * cov) * frame_cov
        if not ctx["deep"] or not (avail["deepfake"] or avail["ai_generated"]):
            conf = min(conf, 0.30)   # only metadata was checked
    else:
        conf = p * (0.75 + 0.25 * cov) * frame_cov
        if verdict == "deepfake" and df is not None:
            conf *= 0.85 + 0.15 * ctx["frac_above"]          # consistent across frames -> more confident
            if ctx["df_frames"] <= 2:
                conf *= 0.85                                  # face seen in only one or two samples
        if partial and verdict in partial:
            conf *= SEGMENT_CONFIDENCE_FACTOR                 # only part of the clip is affected
    conf = max(0.05, min(MAX_CONFIDENCE, conf))

    return {
        "verdict": verdict,
        "authenticity_score": round(float(score), 1),
        "confidence": round(float(conf), 3),
        "summary": _summary(verdict, p, df, ai, ctx, meta, (partial or {}).get(verdict)),
        "uncertainty_note": _uncertainty(verdict, fused, df, ai, ctx, avail, scores, meta,
                                         (partial or {}).get(verdict)),
        "partial_segment": (partial or {}).get(verdict),
        "weights": {k: round(eff_w[k], 4) for k in VIDEO_SIGNAL_ORDER},
        "fused_suspicion": round(float(fused), 4),
    }


def _summary(verdict, p, df, ai, ctx, meta, seg=None) -> str:
    pct = f"{min(p, 0.99) * 100:.0f}%"
    d = meta.get("details") or {}
    if seg is not None:
        span = f"{seg['start_s']:.1f}s to {seg['end_s']:.1f}s"
        what = ("faces look deepfaked or face-swapped" if verdict == "deepfake"
                else "the frames look AI-generated")
        return (f"Part of this video appears synthetic: in {seg['frames']} consecutive sampled frames (about {span}) "
                f"{what} (about {pct} likely), while the rest looks like camera footage. It may be an edited or "
                "spliced clip; the highlighted frames show where the evidence is strongest.")
    if verdict == "deepfake":
        if df is None or df < DEEPFAKE_THRESHOLD:
            return ("The video's metadata names face-swap software (" + ", ".join(d.get("faceswap_hints") or [])
                    + "), so the faces in it were most likely altered.")
        return (f"Faces in this video show the visual fingerprints of deepfake or face-swap synthesis across "
                f"multiple frames (about {pct} likely). The highlighted frames show where the evidence is strongest.")
    if verdict == "ai_generated":
        if ai is None or ai < AI_GENERATED_THRESHOLD:
            return ("The video's metadata names an AI video generator (" + ", ".join(d.get("generator_hints") or [])
                    + "), so it was most likely created by AI rather than filmed with a camera.")
        extra = " Its metadata also names an AI generator." if meta.get("_gen") else ""
        return (f"The frames of this video look like the output of an AI image/video generator rather than a "
                f"camera (about {pct} likely).{extra}")
    if verdict == "manipulated":
        return ("The video shows signs of editing (inconsistent frames or provenance tags), but no strong "
                "deepfake or AI-generation evidence; parts of it may have been altered.")
    if not ctx["deep"] or (df is None and ai is None):
        return ("Only the container metadata could be checked (the deep-learning detectors were unavailable), and "
                "it shows nothing suspicious. This is a partial result, not a confirmation of authenticity.")
    if df is not None and df >= DEEPFAKE_BORDERLINE:
        return (f"No clear signs of deepfakes or AI generation were found, but faces are borderline for the "
                f"deepfake detector ({df * 100:.0f}%), so the video is probably authentic but deserves a closer look.")
    if ai is not None and ai >= AI_BORDERLINE:
        return (f"No faces were flagged, but the AI-image detector is undecided about the frames "
                f"({ai * 100:.0f}%); the video is probably camera footage but deserves a closer look.")
    if df is None:
        return ("No signs of AI generation were found in the sampled frames, and no faces were available for "
                "the deepfake check; the video looks like ordinary camera footage.")
    return ("No significant signs of face-swapping or AI generation were found in the sampled frames; the video "
            "is consistent with ordinary camera footage.")


def _uncertainty(verdict, fused, df, ai, ctx, avail, scores, meta, seg=None) -> str:
    notes = [f"{ctx['frames']} frame{'s' if ctx['frames'] != 1 else ''} were sampled evenly across the video "
             f"(faces found in {ctx['face_frames']}); anything between the samples was not inspected."]
    if not ctx["deep"]:
        notes.append("Deep-learning detectors are disabled on this server, so deepfakes and AI-generated video "
                     "cannot be recognised; only metadata was checked.")
    else:
        missing = [VIDEO_LABELS[k] for k in ("ai_generated", "deepfake") if ctx["model_errors"].get(k)]
        if missing:
            notes.append("Some detectors could not run (" + ", ".join(missing) + "), lowering confidence.")
    if ctx["face_frames"] == 0 and ctx["deep"]:
        notes.append("No faces were found, so the face-deepfake check did not apply.")
    elif ctx["too_small"] and not ctx["df_frames"]:
        notes.append("The faces are too small in the frame to be checked for deepfakes.")
    elif 0 < ctx["df_frames"] <= 2:
        notes.append("A face could only be analysed in one or two of the sampled frames.")
    if seg is not None:
        notes.append(f"Only part of the clip is affected ({seg['frames']} of {ctx['frames']} sampled frames); "
                     "the whole-video average is lower, so the verdict rests on that segment.")
    mf = ctx.get("median_face_px")
    if mf is not None and face_trust(mf) < 1.0:
        notes.append(f"Faces are fairly small in the frame (about {mf:.0f} px); the face model is unreliable on small, "
                     "compressed video faces, so its readings were pulled towards 'undecided' and a deepfake with "
                     "small faces may be missed.")
    if df is not None and DEEPFAKE_BORDERLINE <= df < DEEPFAKE_THRESHOLD:
        notes.append(f"Faces are borderline for the deepfake model ({df * 100:.0f}%); make-up, beauty filters, "
                     "low light and motion blur can look like this.")
    if ai is not None and AI_BORDERLINE <= ai < AI_GENERATED_THRESHOLD and verdict != "ai_generated":
        notes.append(f"The AI-image detector is undecided ({ai * 100:.0f}%); filters, animation, screen recordings "
                     "and heavy compression can confuse it.")
    if verdict == "deepfake" and ai is not None and ai >= AI_GENERATED_THRESHOLD:
        notes.append("The whole-frame AI detector also flags the video, so it may be entirely AI-generated "
                     "rather than a face swap.")
    if verdict in ("deepfake", "ai_generated") and ctx["deep"] and (df is not None or ai is not None):
        notes.append("The detectors were trained on still images, not video; video compression can shift their "
                     "scores.")
    if avail["temporal"] and scores["temporal"] >= STRONG_SIGNAL:
        notes.append("Readings flicker between frames; scene cuts and fast motion also cause this.")
    if meta.get("_gen") and ai is not None and ai < AI_BORDERLINE:
        notes.append("Signals disagree: the metadata names an AI generator, but the frames look camera-like to "
                     "the visual detector.")
    if verdict == "authentic" and 0.35 <= fused < FUSED_SUSPICION_THRESHOLD:
        notes.append("The overall result is close to the decision boundary.")
    if ctx["duration"] and ctx["duration"] < SHORT_VIDEO_S:
        notes.append("The video is very short, so few distinct frames were available.")
    if ctx["frames"] < FEW_FRAMES:
        notes.append("Only a few frames could be analysed.")
    if ctx["min_side"] < LOW_RES_MIN_SIDE:
        notes.append("The video resolution is low, which hides fine detail the detectors rely on.")
    try:
        bpp = ctx["file_size"] * 8.0 / max(1e-6, ctx["duration"]) / max(1.0, ctx["width"] * ctx["height"] * (ctx["fps"] or 25.0))
    except Exception:
        bpp = None
    if bpp is not None and ctx["duration"] and bpp < HEAVY_COMPRESSION_BPP:
        notes.append("The video is heavily compressed, which can hide or mimic manipulation traces.")
    notes.append("All results are probabilistic evidence, not proof.")
    return " ".join(notes)
