"""Tests for backend/app/ml/pipeline.py (contract in docs/CONTRACT.md §4)."""
from __future__ import annotations

import json
import os

import numpy as np
import pytest
from PIL import Image

from app.ml import pipeline

TOP_KEYS = {"verdict", "authenticity_score", "confidence", "uncertainty_note", "summary", "signals", "faces",
            "regions", "metadata", "heatmap_path", "ela_path", "processing_ms", "model_versions"}
SIGNAL_KEYS = {"key", "label", "score", "weight", "available", "explanation", "details"}
REQUIRED_SIGNALS = {"metadata", "ela", "noise", "frequency", "deepfake", "ai_generated"}
VERDICTS = {"authentic", "manipulated", "deepfake", "ai_generated"}


def _assert_plain_json(obj, path="result"):
    """Every value must be a plain Python JSON type (no numpy scalars)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert isinstance(k, str), f"{path} has non-str key {k!r}"
            _assert_plain_json(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _assert_plain_json(v, f"{path}[{i}]")
    else:
        assert obj is None or type(obj) in (str, int, float, bool), f"{path} is {type(obj)}"


def _check_contract(res: dict, image_path: str, out_dir: str):
    assert TOP_KEYS <= set(res), f"missing keys: {TOP_KEYS - set(res)}"
    assert res["verdict"] in VERDICTS
    assert 0 <= res["authenticity_score"] <= 100
    assert 0 <= res["confidence"] <= 1
    assert isinstance(res["summary"], str) and res["summary"]
    assert isinstance(res["uncertainty_note"], str) and res["uncertainty_note"]
    assert isinstance(res["processing_ms"], int) and res["processing_ms"] >= 0
    assert set(res["model_versions"]) >= {"deepfake", "ai_generated"}

    keys = {s["key"] for s in res["signals"]}
    assert REQUIRED_SIGNALS <= keys
    total_w = 0.0
    for s in res["signals"]:
        assert SIGNAL_KEYS <= set(s), s
        assert 0 <= s["score"] <= 1
        assert isinstance(s["available"], bool)
        assert isinstance(s["explanation"], str) and s["explanation"]
        assert isinstance(s["details"], dict)
        if not s["available"]:
            assert s["weight"] == 0
        total_w += s["weight"]
    assert abs(total_w - 1.0) < 1e-3

    with Image.open(image_path) as im:
        w, h = im.size
    md = res["metadata"]
    assert {"format", "width", "height", "exif", "software"} <= set(md)
    assert (md["width"], md["height"]) == (w, h)
    for r in res["regions"]:
        assert set(r) >= {"box", "score", "source"}
        assert r["source"] in {"ela", "noise", "deepfake", "gradcam"}
        x, y, bw, bh = r["box"]
        assert all(isinstance(v, int) for v in r["box"])
        assert 0 <= x < w and 0 <= y < h and bw > 0 and bh > 0 and x + bw <= w and y + bh <= h
        assert 0 <= r["score"] <= 1
    for f in res["faces"]:
        x, y, bw, bh = f["box"]
        assert 0 <= x < w and 0 <= y < h and x + bw <= w and y + bh <= h
        p = f["deepfake_probability"]
        assert p is None or 0 <= p <= 1

    for k in ("heatmap_path", "ela_path"):
        p = res[k]
        assert p is not None, f"{k} missing"
        assert os.path.isabs(p) and os.path.isfile(p)
        assert os.path.dirname(p) == os.path.abspath(out_dir)
        with Image.open(p) as im:
            assert im.format == "PNG"
            # same aspect ratio as the input (heatmap may be downscaled)
            assert abs(im.size[0] / im.size[1] - w / h) < 0.02

    _assert_plain_json(res)
    json.dumps(res)


@pytest.mark.parametrize("name", ["clean", "spliced", "copymove", "png", "rgba", "tiny"])
def test_contract_shape_classical(no_deep, image_dir, tmp_path, name):
    path = image_dir[name]
    res = pipeline.analyze_image(path, str(tmp_path))
    _check_contract(res, path, str(tmp_path))
    by_key = {s["key"]: s for s in res["signals"]}
    assert by_key["deepfake"]["available"] is False
    assert by_key["ai_generated"]["available"] is False
    assert res["model_versions"] == {"deepfake": None, "ai_generated": None}
    assert "disabled" in res["uncertainty_note"].lower()


def test_clean_photo_is_authentic(no_deep, image_dir, tmp_path):
    res = pipeline.analyze_image(image_dir["clean"], str(tmp_path))
    assert res["verdict"] == "authentic", res["summary"]
    assert res["authenticity_score"] >= 70


def test_png_is_not_flagged(no_deep, image_dir, tmp_path):
    res = pipeline.analyze_image(image_dir["png"], str(tmp_path))
    assert res["verdict"] == "authentic", res["summary"]


def test_splice_is_flagged_with_region(no_deep, image_dir, tmp_path):
    res = pipeline.analyze_image(image_dir["spliced"], str(tmp_path))
    assert res["verdict"] == "manipulated", res["signals"]
    assert res["authenticity_score"] < 50
    # at least one forensic region overlaps the pasted patch (x 450-650, y 200-380)
    hits = [r for r in res["regions"] if r["source"] in ("ela", "noise")
            and r["box"][0] < 650 and r["box"][0] + r["box"][2] > 450
            and r["box"][1] < 380 and r["box"][1] + r["box"][3] > 200]
    assert hits, res["regions"]


def test_copymove_is_more_suspicious_than_clean(no_deep, image_dir, tmp_path):
    a = pipeline.analyze_image(image_dir["clean"], str(tmp_path / "a"))
    b = pipeline.analyze_image(image_dir["copymove"], str(tmp_path / "b"))
    assert b["authenticity_score"] < a["authenticity_score"]


def test_metadata_ai_hint_png(no_deep, image_dir, tmp_path):
    from PIL import PngImagePlugin
    info = PngImagePlugin.PngInfo()
    info.add_text("parameters", "a cat, Steps: 20, Sampler: Euler a, CFG scale: 7, Model: sd_xl_base")
    path = str(tmp_path / "sd.png")
    with Image.open(image_dir["png"]) as im:
        im.save(path, "PNG", pnginfo=info)
    res = pipeline.analyze_image(path, str(tmp_path / "out"))
    assert res["verdict"] == "ai_generated"
    meta = next(s for s in res["signals"] if s["key"] == "metadata")
    assert meta["score"] >= 0.9 and meta["details"]["ai_generator_hints"]


def test_exif_orientation_coords(no_deep, image_dir, tmp_path):
    """Image stored landscape with Orientation=6 is displayed portrait; coords must be in display space."""
    with Image.open(image_dir["spliced"]) as im:
        exif = Image.Exif()
        exif[0x0112] = 6
        path = str(tmp_path / "rot.jpg")
        im.save(path, "JPEG", quality=95, exif=exif.tobytes())
    res = pipeline.analyze_image(path, str(tmp_path / "out"))
    assert (res["metadata"]["width"], res["metadata"]["height"]) == (640, 900)
    for r in res["regions"]:
        x, y, w, h = r["box"]
        assert x + w <= 640 and y + h <= 900


def test_corrupt_image_raises_value_error(no_deep, tmp_path):
    p = tmp_path / "bad.jpg"
    p.write_bytes(b"not an image at all")
    with pytest.raises(ValueError):
        pipeline.analyze_image(str(p), str(tmp_path / "out"))


def test_restore_with_boxes(no_deep, image_dir, tmp_path):
    out = str(tmp_path / "restored.png")
    res = pipeline.restore_image(image_dir["spliced"], out, boxes=[[450, 200, 200, 180]])
    assert set(res) >= {"restored_path", "method", "note"}
    assert res["method"] == "opencv_telea"
    assert os.path.isfile(res["restored_path"]) and os.path.abspath(out) == res["restored_path"]
    with Image.open(out) as im, Image.open(image_dir["spliced"]) as orig:
        assert im.format == "PNG" and im.size == orig.size
        a = np.asarray(im.convert("RGB")).astype(int)
        b = np.asarray(orig.convert("RGB")).astype(int)
    # label banner in the top-left corner: dark box with red text
    corner = a[:40, :200]
    assert (corner[..., 0] > 150).sum() > 50 and (corner[..., 1] < 100).sum() > 50
    # in-painted area changed, far-away area essentially unchanged
    assert np.abs(a[260:320, 520:580] - b[260:320, 520:580]).mean() > 3
    assert np.abs(a[500:600, 50:150] - b[500:600, 50:150]).mean() < 2
    json.dumps(res)


def test_restore_with_mask(no_deep, image_dir, tmp_path):
    with Image.open(image_dir["clean"]) as im:
        w, h = im.size
    mask = np.zeros((h // 2, w // 2), np.uint8)   # different size on purpose: must be resized
    mask[100:150, 100:200] = 255
    mp = str(tmp_path / "mask.png")
    Image.fromarray(mask).save(mp)
    out = str(tmp_path / "r.png")
    res = pipeline.restore_image(image_dir["clean"], out, mask_path=mp)
    assert os.path.isfile(out) and res["note"]


def test_restore_auto_regions(no_deep, image_dir, tmp_path):
    out = str(tmp_path / "auto.png")
    res = pipeline.restore_image(image_dir["clean"], out)   # nothing suspicious -> fallback hotspot box
    assert os.path.isfile(out)
    assert "AI-reconstructed" in res["note"]


def test_warmup_without_deep(no_deep):
    pipeline.warmup()   # must not raise or import torch-heavy paths
    assert pipeline.models_loaded() is False


def _deep_models_available() -> bool:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except Exception:
        return False
    from app.ml.detectors.models import DEFAULT_MODELS, get_model
    return all(get_model(k).load() for k in DEFAULT_MODELS)


def test_deep_path(monkeypatch, image_dir, tmp_path):
    monkeypatch.setenv("ML_ENABLE_DEEP", "true")
    if os.environ.get("SKIP_DEEP_TESTS") or not _deep_models_available():
        pytest.skip("deep models unavailable (offline or not downloaded)")
    res = pipeline.analyze_image(image_dir["clean"], str(tmp_path))
    _check_contract(res, image_dir["clean"], str(tmp_path))
    by_key = {s["key"]: s for s in res["signals"]}
    assert by_key["ai_generated"]["available"] is True
    assert res["model_versions"]["ai_generated"]
    assert 0 <= by_key["ai_generated"]["score"] <= 1
    assert res["processing_ms"] < 15000
