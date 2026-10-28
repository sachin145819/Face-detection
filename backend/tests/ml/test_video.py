"""Tests for video analysis (docs/CONTRACT.md §6.2): probe_video / analyze_video."""
from __future__ import annotations

import json
import os
import shutil
import subprocess

import cv2
import numpy as np
import pytest

from app.ml import pipeline, video

TOP_KEYS = {"media_type", "verdict", "authenticity_score", "confidence", "summary", "uncertainty_note", "signals",
            "video", "frames", "top_frames", "faces_detected_frames", "metadata", "processing_ms", "model_versions"}
VIDEO_KEYS = {"duration_s", "fps", "frame_count", "width", "height", "codec", "format"}
FRAME_KEYS = {"index", "timestamp_s", "suspicion", "deepfake_probability", "ai_generated_probability", "faces",
              "thumbnail_path", "heatmap_path"}
SIGNAL_KEYS = {"key", "label", "score", "weight", "available", "explanation", "details"}
VERDICTS = {"authentic", "manipulated", "deepfake", "ai_generated"}
FFMPEG = shutil.which("ffmpeg")

W, H, FPS, SECS = 320, 240, 15, 3


def _write_video(path: str, fourcc: str, red_window: tuple[float, float] | None = None) -> str:
    """Moving shapes on a gradient. Frames whose time falls in red_window get a strongly red background."""
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*fourcc), FPS, (W, H))
    assert vw.isOpened(), f"VideoWriter could not open {path}"
    n = FPS * SECS
    for i in range(n):
        f = np.full((H, W, 3), 60, np.uint8)
        f[:, :, 1] = np.linspace(40, 200, W, dtype=np.uint8)[None, :]
        if red_window and red_window[0] <= i / n < red_window[1]:
            f[:, :, 2] = 250
            f[:, :, 1] = 10
        cv2.circle(f, (int(20 + i * 5) % W, H // 2), 25, (0, 0, 255), -1)
        cv2.rectangle(f, (50, int(10 + i * 3) % H), (90, int(50 + i * 3) % H), (255, 255, 0), -1)
        vw.write(f)
    vw.release()
    return path


@pytest.fixture(scope="module")
def videos(tmp_path_factory):
    d = tmp_path_factory.mktemp("videos")
    out = {"mp4": _write_video(str(d / "clip.mp4"), "mp4v"), "avi": _write_video(str(d / "clip.avi"), "MJPG"),
           "spliced": _write_video(str(d / "spliced.mp4"), "mp4v", red_window=(0.35, 0.70))}
    return out


def _assert_plain_json(obj, path="result"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert isinstance(k, str), f"{path} has non-str key {k!r}"
            _assert_plain_json(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _assert_plain_json(v, f"{path}[{i}]")
    else:
        assert obj is None or type(obj) in (str, int, float, bool), f"{path} is {type(obj)}"


def _check_contract(res: dict, out_dir: str, max_frames: int = 16):
    assert TOP_KEYS <= set(res), f"missing keys: {TOP_KEYS - set(res)}"
    _assert_plain_json(res)
    json.dumps(res)
    assert res["media_type"] == "video"
    assert res["verdict"] in VERDICTS
    assert 0 <= res["authenticity_score"] <= 100
    assert 0 <= res["confidence"] <= 1
    assert res["summary"] and res["uncertainty_note"]
    assert isinstance(res["processing_ms"], int) and res["processing_ms"] >= 0
    assert set(res["model_versions"]) >= {"deepfake", "ai_generated"}
    assert VIDEO_KEYS <= set(res["video"])
    assert {"encoder", "generator_hint", "tags"} <= set(res["metadata"])

    keys = [s["key"] for s in res["signals"]]
    assert set(keys) == {"deepfake", "ai_generated", "temporal", "metadata"}
    total = 0.0
    for s in res["signals"]:
        assert SIGNAL_KEYS <= set(s)
        assert 0 <= s["score"] <= 1 and 0 <= s["weight"] <= 1
        if not s["available"]:
            assert s["weight"] == 0
        total += s["weight"]
    assert abs(total - 1.0) < 1e-3

    frames = res["frames"]
    assert 1 <= len(frames) <= max_frames
    vw, vh = res["video"]["width"], res["video"]["height"]
    ts = [f["timestamp_s"] for f in frames]
    assert ts == sorted(ts) and len(set(ts)) == len(ts), "frames must be ordered by time"
    for i, f in enumerate(frames):
        assert FRAME_KEYS <= set(f)
        assert f["index"] == i
        assert 0 <= f["suspicion"] <= 1
        assert 0 <= f["timestamp_s"] <= res["video"]["duration_s"] + 0.5
        assert f["thumbnail_path"] and os.path.isfile(f["thumbnail_path"])
        assert os.path.dirname(f["thumbnail_path"]) == os.path.abspath(out_dir)
        with open(f["thumbnail_path"], "rb") as fh:
            assert fh.read(3) == b"\xff\xd8\xff"
        th = cv2.imread(f["thumbnail_path"])
        assert max(th.shape[:2]) <= 640
        for face in f["faces"]:
            x, y, w, h = face["box"]
            assert all(isinstance(v, int) for v in face["box"])
            assert 0 <= x and 0 <= y and w > 0 and h > 0 and x + w <= vw and y + h <= vh
    top = res["top_frames"]
    assert 1 <= len(top) <= 4 and len(set(top)) == len(top)
    assert all(0 <= i < len(frames) for i in top)
    sus = [frames[i]["suspicion"] for i in top]
    assert sus == sorted(sus, reverse=True), "top_frames must be most suspicious first"
    for i, f in enumerate(frames):
        if i in top:
            assert f["heatmap_path"] and os.path.isfile(f["heatmap_path"])
        else:
            assert f["heatmap_path"] is None
    assert res["faces_detected_frames"] == sum(1 for f in frames if f["faces"])


# ------------------------------------------------------------------ probe
@pytest.mark.parametrize("kind,codec,fmt", [("mp4", "mpeg4", "mp4"), ("avi", "mjpeg", "avi")])
def test_probe_values(videos, kind, codec, fmt):
    info = pipeline.probe_video(videos[kind])
    assert set(info) == VIDEO_KEYS
    _assert_plain_json(info)
    assert (info["width"], info["height"]) == (W, H)
    assert info["fps"] == pytest.approx(FPS, abs=0.01)
    assert abs(info["frame_count"] - FPS * SECS) <= 1
    assert info["duration_s"] == pytest.approx(SECS, abs=0.15)
    assert info["codec"] == codec
    assert info["format"] == fmt


@pytest.mark.parametrize("content", [b"hello, this is not a video at all" * 10, b"\x00" * 5000])
def test_probe_rejects_non_video(tmp_path, content):
    p = tmp_path / "fake.mp4"
    p.write_bytes(content)
    with pytest.raises(ValueError):
        pipeline.probe_video(str(p))
    with pytest.raises(ValueError):
        pipeline.analyze_video(str(p), str(tmp_path / "out"))


def test_probe_rejects_still_image_and_missing(tmp_path):
    img = tmp_path / "still.jpg"
    cv2.imwrite(str(img), np.full((64, 64, 3), 128, np.uint8))
    with pytest.raises(ValueError):
        pipeline.probe_video(str(img))
    with pytest.raises(ValueError):
        pipeline.probe_video(str(tmp_path / "missing.mp4"))


def test_truncated_video_raises(videos, tmp_path):
    data = open(videos["mp4"], "rb").read()
    p = tmp_path / "trunc.mp4"
    p.write_bytes(data[:200])
    with pytest.raises(ValueError):
        pipeline.probe_video(str(p))


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")
def test_rotated_phone_video_reports_display_size(videos, tmp_path):
    h264 = tmp_path / "h264.mp4"
    rot = tmp_path / "rot.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", videos["mp4"], "-c:v", "libx264", str(h264)], check=True)
    r = subprocess.run([FFMPEG, "-v", "error", "-y", "-display_rotation", "90", "-i", str(h264), "-c", "copy",
                        str(rot)])
    if r.returncode != 0:
        pytest.skip("this ffmpeg cannot write rotation metadata")
    info = pipeline.probe_video(str(rot))
    assert (info["width"], info["height"]) == (H, W)
    res = pipeline.analyze_video(str(rot), str(tmp_path / "out"), max_frames=4)
    th = cv2.imread(res["frames"][0]["thumbnail_path"])
    assert th.shape[0] > th.shape[1]   # portrait thumbnail


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")
def test_webm_without_frame_count(no_deep, videos, tmp_path, monkeypatch):
    """Streamed WebM has no duration/cues: OpenCV reports a bogus frame count; we must fall back."""
    p = tmp_path / "live.webm"
    with open(p, "wb") as fh:
        r = subprocess.run([FFMPEG, "-v", "error", "-i", videos["mp4"], "-c:v", "libvpx", "-b:v", "300k",
                            "-f", "webm", "pipe:1"], stdout=fh)
    if r.returncode != 0:
        pytest.skip("ffmpeg without libvpx")
    monkeypatch.setenv("PATH", "/nonexistent")   # no ffprobe either
    info = pipeline.probe_video(str(p))
    assert info["format"] == "webm" and info["codec"] == "vp8"
    assert abs(info["frame_count"] - FPS * SECS) <= 1
    assert info["duration_s"] == pytest.approx(SECS, abs=0.2)
    res = pipeline.analyze_video(str(p), str(tmp_path / "out"), max_frames=8)
    _check_contract(res, str(tmp_path / "out"), 8)
    assert len(res["frames"]) == 8


# ------------------------------------------------------------------ analyze (classical / no deep models)
@pytest.mark.parametrize("kind", ["mp4", "avi"])
def test_analyze_video_contract_without_deep(no_deep, videos, tmp_path, kind):
    out = str(tmp_path / "out")
    res = pipeline.analyze_video(videos[kind], out)
    _check_contract(res, out)
    assert len(res["frames"]) == 16
    by = {s["key"]: s for s in res["signals"]}
    assert by["deepfake"]["available"] is False
    assert by["ai_generated"]["available"] is False
    assert by["metadata"]["available"] is True
    assert res["model_versions"] == {"deepfake": None, "ai_generated": None}
    assert res["verdict"] == "authentic"
    assert res["confidence"] <= 0.30
    assert "disabled" in res["uncertainty_note"]
    assert all(f["ai_generated_probability"] is None for f in res["frames"])
    assert res["video"] == pipeline.probe_video(videos[kind])


def test_max_frames_param_and_env(no_deep, videos, tmp_path, monkeypatch):
    res = pipeline.analyze_video(videos["mp4"], str(tmp_path / "a"), max_frames=5)
    assert len(res["frames"]) == 5
    monkeypatch.setenv("VIDEO_MAX_FRAMES", "7")
    res = pipeline.analyze_video(videos["mp4"], str(tmp_path / "b"))
    assert len(res["frames"]) == 7
    # more samples than frames in the clip -> one sample per frame, no duplicates
    res = pipeline.analyze_video(videos["mp4"], str(tmp_path / "c"), max_frames=60)
    assert len(res["frames"]) == FPS * SECS
    assert len({f["frame_number"] for f in res["frames"]}) == FPS * SECS


def test_metadata_generator_hint(no_deep, videos, tmp_path):
    if not FFMPEG:
        pytest.skip("ffmpeg not installed")
    p = tmp_path / "sora.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", videos["mp4"], "-c", "copy", "-metadata",
                    "comment=Generated with OpenAI Sora", str(p)], check=True)
    res = pipeline.analyze_video(str(p), str(tmp_path / "out"), max_frames=4)
    assert res["metadata"]["generator_hint"] == "OpenAI Sora"
    assert res["verdict"] == "ai_generated"


# ------------------------------------------------------------------ aggregation
def test_robust_aggregate_resists_single_outlier():
    assert video.robust_aggregate([0.1] * 15 + [0.99], video.DEEPFAKE_TOPK_BLEND) < 0.4
    assert video.robust_aggregate([0.9] * 16, video.DEEPFAKE_TOPK_BLEND) == pytest.approx(0.9)
    assert video.robust_aggregate([0.5], 0.75) == 0.5
    assert video.robust_aggregate([], 0.75) == 0.0


def test_face_calibration_shrinks_small_faces():
    assert video.calibrate_face_probability(0.95, 120) < video.DEEPFAKE_THRESHOLD
    assert video.calibrate_face_probability(0.95, 500) == pytest.approx(0.95)
    assert video.calibrate_face_probability(0.1, 500) == pytest.approx(0.1)


def _series(key, vals):
    return [{key: v, "timestamp_s": float(i)} for i, v in enumerate(vals)]


def test_find_segment():
    k = "deepfake_probability"
    seg = video.find_segment(_series(k, [0.2] * 5 + [0.77, 0.77, 0.72, 0.8, 0.67, 0.72] + [0.2] * 5), k, 0.72)
    assert seg and seg["start_index"] == 5 and seg["end_index"] == 10 and seg["partial"]
    # a real clip hovering just under the bar, isolated spikes, or runs broken by missing faces don't count
    assert video.find_segment(_series(k, [0.68, 0.6, 0.65] * 5), k, 0.72) is None
    assert video.find_segment(_series(k, [0.9, 0.9, 0.2] * 5), k, 0.72) is None
    assert video.find_segment(_series(k, [0.9, 0.9, None, 0.9, 0.9] + [0.1] * 11), k, 0.72) is None


def test_partially_ai_generated_clip_is_flagged(videos, tmp_path, monkeypatch):
    """A spliced clip whose middle third is AI-generated must not be diluted to 'authentic'."""
    monkeypatch.setenv("ML_ENABLE_DEEP", "true")

    def fake_ai(rgb):
        red = float(rgb[..., 0].mean()) > 200 and float(rgb[..., 1].mean()) < 60
        p = 0.99 if red else 0.02
        return {"key": "ai_generated", "label": "x", "score": p, "available": True, "explanation": "stub",
                "details": {}}, None

    monkeypatch.setattr(video, "analyze_ai_generated", fake_ai)
    out = str(tmp_path / "out")
    res = pipeline.analyze_video(videos["spliced"], out)
    _check_contract(res, out)
    by = {s["key"]: s for s in res["signals"]}
    assert by["ai_generated"]["score"] < video.AI_GENERATED_THRESHOLD   # the whole-video aggregate is diluted ...
    assert res["verdict"] == "ai_generated"                              # ... but the segment decides
    seg = res["partial_segment"]
    assert seg and seg["partial"] and seg["frames"] >= video.SEGMENT_MIN_FRAMES
    assert "Part of this video" in res["summary"]
    assert "Only part of the clip" in res["uncertainty_note"]
    flagged = [i for i, f in enumerate(res["frames"]) if f["ai_generated_probability"] > 0.5]
    assert set(res["top_frames"]) <= set(flagged)

    # control: the unspliced clip stays authentic with the same stub
    res2 = pipeline.analyze_video(videos["mp4"], str(tmp_path / "out2"))
    assert res2["verdict"] == "authentic" and res2["partial_segment"] is None


# ------------------------------------------------------------------ deep path
def _deep_models_available() -> bool:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except Exception:
        return False
    from app.ml.detectors.models import DEFAULT_MODELS, get_model
    return all(get_model(k).load() for k in DEFAULT_MODELS)


def test_deep_path(monkeypatch, videos, tmp_path):
    monkeypatch.setenv("ML_ENABLE_DEEP", "true")
    if os.environ.get("SKIP_DEEP_TESTS") or not _deep_models_available():
        pytest.skip("deep models unavailable (offline or not downloaded)")
    out = str(tmp_path / "out")
    res = pipeline.analyze_video(videos["mp4"], out, max_frames=6)
    _check_contract(res, out, 6)
    by = {s["key"]: s for s in res["signals"]}
    assert by["ai_generated"]["available"] is True
    assert by["temporal"]["available"] is True
    assert res["model_versions"]["ai_generated"]
    assert all(f["ai_generated_probability"] is not None for f in res["frames"])
    assert res["processing_ms"] < 30000
