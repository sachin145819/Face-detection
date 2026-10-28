"""Video upload / analysis / report / history / dashboard (docs/CONTRACT.md §6).

Uses the real app.ml.pipeline.probe_video / analyze_video when they exist; otherwise a cv2-based
fake with the same contract is monkeypatched into app.services.ml.
"""
import os
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import pytest

from tl_helpers import auth_headers, make_png, register, upload

VERDICTS = {"authentic", "manipulated", "deepfake", "ai_generated"}
VIDEO_OUT_KEYS = {"id", "original_filename", "mime_type", "size_bytes", "width", "height", "duration_s", "fps",
                  "frame_count", "uploaded_at", "url"}


# ------------------------------------------------------------------ fake ML (only if missing)
def _fake_probe(video_path: str) -> dict:
    cap = cv2.VideoCapture(video_path)
    try:
        if not cap.isOpened():
            raise ValueError("cannot open video")
        ok, frame = cap.read()
        if not ok or frame is None:
            raise ValueError("no decodable frames")
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        h, w = frame.shape[:2]
    finally:
        cap.release()
    return {"duration_s": n / fps if fps else 0.0, "fps": fps, "frame_count": n, "width": w, "height": h,
            "codec": "mp4v", "format": "mp4"}


def _fake_analyze(video_path: str, output_dir: str, max_frames=None) -> dict:
    info = _fake_probe(video_path)
    cap = cv2.VideoCapture(video_path)
    frames = []
    i = 0
    while len(frames) < (max_frames or 16):
        ok, img = cap.read()
        if not ok:
            break
        thumb = os.path.join(output_dir, f"frame_{i:03d}.jpg")
        cv2.imwrite(thumb, img)
        heat = None
        if i % 2 == 0:
            heat = os.path.join(output_dir, f"frame_{i:03d}_heat.jpg")
            cv2.imwrite(heat, 255 - img)
        frames.append({"index": i, "timestamp_s": i / (info["fps"] or 1), "suspicion": np.float32(0.1 + 0.05 * i),
                       "deepfake_probability": None if i % 3 else 0.4, "ai_generated_probability": 0.2,
                       "faces": [{"box": [2, 2, 20, 20], "deepfake_probability": 0.4}] if i % 3 == 0 else [],
                       "thumbnail_path": thumb, "heatmap_path": heat})
        i += 1
    cap.release()
    return {
        "media_type": "video", "verdict": "deepfake", "authenticity_score": 31.0, "confidence": 0.7,
        "summary": "Fake summary.", "uncertainty_note": "Fake note.",
        "signals": [{"key": k, "label": k.title(), "score": 0.3, "weight": 0.25, "available": k != "metadata",
                     "explanation": "x", "details": {}} for k in ("deepfake", "ai_generated", "temporal", "metadata")],
        "video": info, "frames": frames, "top_frames": [len(frames) - 1, 0] if frames else [],
        "faces_detected_frames": sum(1 for f in frames if f["faces"]),
        "metadata": {"encoder": "Lavf", "generator_hint": None, "tags": {"major_brand": "isom"}},
        "processing_ms": 12, "model_versions": {"deepfake": None, "ai_generated": None},
        "score_nan": float("nan"),
    }


@pytest.fixture()
def video_ml(monkeypatch):
    """Patch app.services.ml with fakes only when the real pipeline lacks video support."""
    from app.ml import pipeline
    from app.services import ml

    real = callable(getattr(pipeline, "probe_video", None)) and callable(getattr(pipeline, "analyze_video", None))
    if not real:
        monkeypatch.setattr(ml, "probe_video", _fake_probe)
        monkeypatch.setattr(ml, "analyze_video", _fake_analyze)
    return real


def _write_mp4(path: Path, size=(160, 120), n=20, fps=10.0) -> bytes:
    w, h = size
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    assert vw.isOpened(), "cv2.VideoWriter could not open mp4v"
    for i in range(n):
        frame = np.zeros((h, w, 3), np.uint8)
        frame[:, :] = (30, (60 + i * 5) % 256, (200 - i * 5) % 256)
        x0 = (10 + i * 3) % max(1, w - 40)
        cv2.rectangle(frame, (x0, 20), (x0 + 40, 70), (255, 255, 255), -1)
        cv2.putText(frame, str(i), (5, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        vw.write(frame)
    vw.release()
    return path.read_bytes()


@pytest.fixture(scope="module")
def mp4_bytes(tmp_path_factory) -> bytes:
    return _write_mp4(tmp_path_factory.mktemp("vid") / "tiny.mp4")


def upload_video(client, token, data, filename="clip.mp4", mime="video/mp4"):
    return client.post("/api/videos", files={"file": (filename, data, mime)}, headers=auth_headers(token))


def _storage() -> Path:
    return Path(os.environ["STORAGE_DIR"])


# ------------------------------------------------------------------ upload validation
def test_upload_rejects_bad_extension(client, token, video_ml, mp4_bytes):
    r = upload_video(client, token, mp4_bytes, "clip.gif", "image/gif")
    assert r.status_code == 400 and isinstance(r.json()["detail"], str)
    r = upload_video(client, token, mp4_bytes, "clip.mp4", "image/png")
    assert r.status_code == 400


def test_upload_rejects_non_video_bytes(client, token, video_ml):
    r = upload_video(client, token, b"definitely not a video " * 100, "evil.mp4")
    assert r.status_code == 400, r.text
    assert not any((_storage() / "videos").glob("*")), "rejected upload must not stay on disk"
    assert client.get("/api/videos", headers=auth_headers(token)).json() == []


def test_upload_empty_and_too_large(client, token, video_ml, monkeypatch):
    from app.config import get_settings

    assert upload_video(client, token, b"", "e.mp4").status_code == 400
    monkeypatch.setenv("MAX_VIDEO_MB", "1")
    get_settings.cache_clear()
    r = upload_video(client, token, os.urandom(1024 * 1024 + 10), "big.mp4")
    assert r.status_code == 413
    assert not any((_storage() / "videos").glob("*"))


def test_upload_requires_auth(client, mp4_bytes):
    assert client.post("/api/videos", files={"file": ("a.mp4", mp4_bytes, "video/mp4")}).status_code == 401


# ------------------------------------------------------------------ upload / file / range
def test_upload_list_get_and_range(client, token, video_ml, mp4_bytes):
    h = auth_headers(token)
    r = upload_video(client, token, mp4_bytes, "My Clip.mp4", "application/octet-stream")
    assert r.status_code == 201, r.text
    v = r.json()
    assert set(v) == VIDEO_OUT_KEYS
    assert v["mime_type"] == "video/mp4" and v["original_filename"] == "My Clip.mp4"
    assert (v["width"], v["height"]) == (160, 120)
    assert v["size_bytes"] == len(mp4_bytes)
    assert v["fps"] > 0 and v["duration_s"] > 0 and v["frame_count"] > 0
    assert v["url"] == f"/api/videos/{v['id']}/file"

    assert [x["id"] for x in client.get("/api/videos", headers=h).json()] == [v["id"]]
    assert client.get(f"/api/videos/{v['id']}", headers=h).json()["id"] == v["id"]

    full = client.get(f"{v['url']}?token={token}")
    assert full.status_code == 200 and full.content == mp4_bytes
    assert full.headers["content-type"] == "video/mp4"
    assert full.headers.get("accept-ranges") == "bytes"
    part = client.get(v["url"], headers={**h, "Range": "bytes=0-99"})
    assert part.status_code == 206
    assert part.content == mp4_bytes[:100]
    assert part.headers["content-range"] == f"bytes 0-99/{len(mp4_bytes)}"
    tail = client.get(f"{v['url']}?token={token}", headers={"Range": "bytes=100-"})
    assert tail.status_code == 206 and tail.content == mp4_bytes[100:]
    assert client.get(v["url"]).status_code == 401

    # other upload types
    r = upload_video(client, token, mp4_bytes, "clip.MOV", "video/quicktime")
    assert r.status_code == 201 and r.json()["mime_type"] == "video/quicktime"


def test_video_isolation(client, token, video_ml, mp4_bytes):
    v = upload_video(client, token, mp4_bytes).json()
    a = client.post("/api/video-analyses", json={"video_id": v["id"]}, headers=auth_headers(token)).json()
    bob = register(client, email="bob@example.com", name="Bob")["access_token"]
    hb = auth_headers(bob)
    assert client.get("/api/videos", headers=hb).json() == []
    for url in (f"/api/videos/{v['id']}", f"/api/videos/{v['id']}/file", f"/api/video-analyses/{a['id']}",
                f"/api/video-analyses/{a['id']}/report"):
        assert client.get(url, headers=hb).status_code == 404, url
    assert client.get(f"/api/videos/{v['id']}/file?token={bob}").status_code == 404
    assert client.delete(f"/api/videos/{v['id']}", headers=hb).status_code == 404
    assert client.post("/api/video-analyses", json={"video_id": v["id"]}, headers=hb).status_code == 404
    assert client.get("/api/history", headers=hb).json()["total"] == 0
    assert client.get(f"/api/videos/{v['id']}", headers=auth_headers(token)).status_code == 200


# ------------------------------------------------------------------ full flow
def test_video_analysis_flow(client, token, video_ml, mp4_bytes):
    h = auth_headers(token)
    v = upload_video(client, token, mp4_bytes, "suspect-clip.mp4").json()
    r = client.post("/api/video-analyses", json={"video_id": v["id"]}, headers=h)
    assert r.status_code == 201, r.text
    a = r.json()
    for k in ("id", "video_id", "verdict", "authenticity_score", "confidence", "created_at", "processing_ms",
              "result", "video", "report_url"):
        assert k in a, k
    assert a["verdict"] in VERDICTS
    assert 0 <= a["authenticity_score"] <= 100 and 0 <= a["confidence"] <= 1
    assert a["video_id"] == v["id"] and a["video"]["id"] == v["id"]
    assert a["report_url"] == f"/api/video-analyses/{a['id']}/report"
    res = a["result"]
    assert res["media_type"] == "video"
    for k in ("verdict", "summary", "uncertainty_note", "signals", "video", "frames", "top_frames",
              "faces_detected_frames", "metadata", "model_versions"):
        assert k in res, k
    assert "_path" not in r.text, "server paths must never leak"
    assert res["frames"], "expected at least one sampled frame"
    for f in res["frames"]:
        assert "thumbnail_path" not in f and "heatmap_path" not in f
        assert "thumbnail_url" in f and "heatmap_url" in f
    thumb_urls = [f["thumbnail_url"] for f in res["frames"] if f["thumbnail_url"]]
    assert thumb_urls
    assert all(u.startswith(f"/api/video-analyses/{a['id']}/files/") for u in thumb_urls)

    # frame files are served (bearer + ?token=), no tmp dirs left
    fr = client.get(f"{thumb_urls[0]}?token={token}")
    assert fr.status_code == 200 and fr.headers["content-type"].startswith("image/")
    assert client.get(thumb_urls[0], headers=h).status_code == 200
    assert client.get(thumb_urls[0]).status_code == 401
    for f in res["frames"]:
        if f["heatmap_url"]:
            assert client.get(f["heatmap_url"], headers=h).status_code == 200
    vdir = _storage() / "video_analyses"
    assert (vdir / str(a["id"])).is_dir()
    assert not [p for p in vdir.iterdir() if p.name.startswith("tmp-")]

    # path traversal / non-existent names are rejected
    base = f"/api/video-analyses/{a['id']}/files/"
    for bad in ("..%2F..%2Fsession.db", "%2E%2E", "nope.jpg", "..%5Cfoo", ".hidden",
                "%2Fetc%2Fpasswd", "..%2Fvideos"):
        assert client.get(base + bad, headers=h).status_code == 404, bad

    got = client.get(f"/api/video-analyses/{a['id']}", headers=h)
    assert got.status_code == 200 and got.json()["result"] == res
    assert client.get("/api/video-analyses/99999", headers=h).status_code == 404
    assert client.post("/api/video-analyses", json={"video_id": 99999}, headers=h).status_code == 404

    # PDF report (generated once, cached)
    pdf = client.get(f"{a['report_url']}?token={token}")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert pdf.headers["content-type"] == "application/pdf"
    assert len(pdf.content) > 3000
    assert (_storage() / "reports" / f"video-report-{a['id']}.pdf").is_file()
    assert client.get(a["report_url"], headers=h).content == pdf.content

    # mixed history: one image analysis + the video analysis
    img = upload(client, token, make_png((96, 64)), "holiday.png").json()
    ia = client.post("/api/analyses", json={"image_id": img["id"]}, headers=h)
    assert ia.status_code == 201, ia.text
    ia = ia.json()
    hist = client.get("/api/history", headers=h).json()
    assert hist["total"] == 2
    kinds = [i["media_type"] for i in hist["items"]]
    assert kinds == ["image", "video"]  # newest first
    vitem = hist["items"][1]
    assert vitem["analysis_id"] == a["id"] and vitem["video_id"] == v["id"] and vitem["image_id"] is None
    assert vitem["original_filename"] == "suspect-clip.mp4"
    assert vitem["thumbnail_url"] is None or vitem["thumbnail_url"].startswith(base)
    iitem = hist["items"][0]
    assert iitem["analysis_id"] == ia["id"] and iitem["image_id"] == img["id"] and iitem["video_id"] is None
    assert iitem["thumbnail_url"] == f"/api/images/{img['id']}/file"

    only_v = client.get("/api/history", params={"media": "video"}, headers=h).json()
    assert only_v["total"] == 1 and only_v["items"][0]["media_type"] == "video"
    only_i = client.get("/api/history", params={"media": "image"}, headers=h).json()
    assert only_i["total"] == 1 and only_i["items"][0]["media_type"] == "image"
    assert client.get("/api/history", params={"media": ""}, headers=h).json()["total"] == 2
    assert client.get("/api/history", params={"media": "audio"}, headers=h).status_code == 400
    q = client.get("/api/history", params={"q": "SUSPECT"}, headers=h).json()
    assert q["total"] == 1 and q["items"][0]["media_type"] == "video"
    vv = client.get("/api/history", params={"verdict": a["verdict"], "media": "video"}, headers=h).json()
    assert vv["total"] == 1
    other = next(x for x in VERDICTS if x != a["verdict"])
    assert client.get("/api/history", params={"verdict": other, "media": "video"}, headers=h).json()["total"] == 0
    p2 = client.get("/api/history", params={"page": 2, "page_size": 1}, headers=h).json()
    assert p2["total"] == 2 and [i["media_type"] for i in p2["items"]] == ["video"]

    # dashboard
    s = client.get("/api/dashboard/stats", headers=h).json()
    assert s["total_images"] == 1 and s["total_videos"] == 1 and s["total_analyses"] == 2
    assert s["by_media"] == {"image": 1, "video": 1}
    assert sum(s["by_verdict"].values()) == 2
    today = datetime.now(timezone.utc).date().isoformat()
    assert s["trend"][-1]["date"] == today and sum(s["trend"][-1][k] for k in VERDICTS) == 2
    assert [i["media_type"] for i in s["recent"]] == ["image", "video"]
    expected_avg = round((a["authenticity_score"] + ia["authenticity_score"]) / 2, 2)
    assert abs(s["avg_authenticity_score"] - expected_avg) < 0.01

    # delete cascades: rows, analysis dir, report, video file
    stored = list((_storage() / "videos").glob("*"))
    assert len(stored) == 1
    assert client.delete(f"/api/videos/{v['id']}", headers=h).status_code == 204
    assert client.get(f"/api/videos/{v['id']}", headers=h).status_code == 404
    assert client.get(f"/api/video-analyses/{a['id']}", headers=h).status_code == 404
    assert not stored[0].exists()
    assert not (vdir / str(a["id"])).exists()
    assert not (_storage() / "reports" / f"video-report-{a['id']}.pdf").exists()
    hist = client.get("/api/history", headers=h).json()
    assert hist["total"] == 1 and hist["items"][0]["media_type"] == "image"
    s = client.get("/api/dashboard/stats", headers=h).json()
    assert s["total_videos"] == 0 and s["by_media"] == {"image": 1, "video": 0}


def test_analysis_errors_leave_no_rows(client, token, video_ml, mp4_bytes, monkeypatch):
    from app.services import ml

    h = auth_headers(token)
    v = upload_video(client, token, mp4_bytes).json()

    def bad_value(*_a, **_k):
        raise ValueError("unreadable stream")

    def boom(*_a, **_k):
        raise RuntimeError("model exploded")

    monkeypatch.setattr(ml, "analyze_video", bad_value)
    r = client.post("/api/video-analyses", json={"video_id": v["id"]}, headers=h)
    assert r.status_code == 400 and "unreadable stream" in r.json()["detail"]
    monkeypatch.setattr(ml, "analyze_video", boom)
    r = client.post("/api/video-analyses", json={"video_id": v["id"]}, headers=h)
    assert r.status_code == 500 and "model exploded" in r.json()["detail"]
    assert client.get("/api/history", params={"media": "video"}, headers=h).json()["total"] == 0
    vdir = _storage() / "video_analyses"
    assert not vdir.exists() or not list(vdir.iterdir())


def test_fake_result_sanitised_and_report(client, token, mp4_bytes, monkeypatch):
    """Always exercise the rich fake (numpy floats, NaN, heatmaps, faces) through serializer + PDF."""
    from app.services import ml

    monkeypatch.setattr(ml, "probe_video", _fake_probe)
    monkeypatch.setattr(ml, "analyze_video", _fake_analyze)
    h = auth_headers(token)
    v = upload_video(client, token, mp4_bytes).json()
    a = client.post("/api/video-analyses", json={"video_id": v["id"]}, headers=h)
    assert a.status_code == 201, a.text
    a = a.json()
    assert a["result"]["score_nan"] is None
    assert isinstance(a["result"]["frames"][0]["suspicion"], float)
    assert a["result"]["frames"][0]["heatmap_url"] and a["result"]["frames"][1]["heatmap_url"] is None
    item = client.get("/api/history", headers=h).json()["items"][0]
    top = a["result"]["frames"][a["result"]["top_frames"][0]]
    assert item["thumbnail_url"] == top["thumbnail_url"]
    pdf = client.get(a["report_url"], headers=h)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and len(pdf.content) > 10000
