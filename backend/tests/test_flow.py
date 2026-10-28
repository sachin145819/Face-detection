import base64
import io
from datetime import datetime, timezone

from PIL import Image as PILImage

from tl_helpers import auth_headers, make_png, upload

VERDICTS = {"authentic", "manipulated", "deepfake", "ai_generated"}


def _analyze(client, token, image_id):
    r = client.post("/api/analyses", json={"image_id": image_id}, headers=auth_headers(token))
    assert r.status_code == 201, r.text
    return r.json()


def test_analysis_history_dashboard_report(client, token):
    h = auth_headers(token)
    img = upload(client, token, make_png((128, 96)), "holiday-photo.png").json()
    a = _analyze(client, token, img["id"])

    # AnalysisOut shape
    for k in ("id", "image_id", "verdict", "authenticity_score", "confidence", "created_at", "processing_ms",
              "result", "image", "heatmap_url", "ela_url", "report_url", "restorations"):
        assert k in a, k
    assert a["verdict"] in VERDICTS
    assert 0 <= a["authenticity_score"] <= 100
    assert 0 <= a["confidence"] <= 1
    assert "heatmap_path" not in a["result"] and "ela_path" not in a["result"]
    for k in ("verdict", "summary", "signals", "faces", "regions", "metadata", "uncertainty_note"):
        assert k in a["result"], k
    assert a["image"]["id"] == img["id"]
    assert a["report_url"] == f"/api/reports/{a['id']}/pdf"
    assert a["restorations"] == []
    for key, path in (("heatmap_url", "heatmap"), ("ela_url", "ela")):
        if a[key] is not None:
            assert a[key] == f"/api/analyses/{a['id']}/{path}"
            r = client.get(f"{a[key]}?token={token}")
            assert r.status_code == 200 and r.headers["content-type"] == "image/png"
        else:
            assert client.get(f"/api/analyses/{a['id']}/{path}", headers=h).status_code == 404

    got = client.get(f"/api/analyses/{a['id']}", headers=h)
    assert got.status_code == 200 and got.json()["id"] == a["id"]

    # second image + analysis for history filtering
    img2 = upload(client, token, make_png((80, 80), (10, 120, 200)), "other.png").json()
    a2 = _analyze(client, token, img2["id"])

    hist = client.get("/api/history", headers=h).json()
    assert hist["total"] == 2 and hist["page"] == 1 and hist["page_size"] == 10
    assert [i["analysis_id"] for i in hist["items"]] == [a2["id"], a["id"]]
    item = hist["items"][1]
    assert set(item) >= {"analysis_id", "image_id", "original_filename", "verdict", "authenticity_score",
                         "confidence", "created_at", "thumbnail_url"}
    assert item["thumbnail_url"] == f"/api/images/{img['id']}/file"
    assert item["media_type"] == "image" and item["video_id"] is None

    q = client.get("/api/history", params={"q": "HOLIDAY"}, headers=h).json()
    assert q["total"] == 1 and q["items"][0]["analysis_id"] == a["id"]
    v = client.get("/api/history", params={"verdict": a["verdict"]}, headers=h).json()
    assert a["id"] in [i["analysis_id"] for i in v["items"]]
    other = next(x for x in VERDICTS if x not in {a["verdict"], a2["verdict"]})
    assert client.get("/api/history", params={"verdict": other}, headers=h).json()["total"] == 0
    p = client.get("/api/history", params={"page": 2, "page_size": 1}, headers=h).json()
    assert p["total"] == 2 and len(p["items"]) == 1 and p["items"][0]["analysis_id"] == a["id"]
    assert client.get("/api/history", params={"verdict": "bogus"}, headers=h).status_code == 400

    stats = client.get("/api/dashboard/stats", headers=h).json()
    assert stats["total_images"] == 2 and stats["total_analyses"] == 2
    assert set(stats["by_verdict"]) == VERDICTS
    assert sum(stats["by_verdict"].values()) == 2
    assert len(stats["trend"]) == 7
    today = datetime.now(timezone.utc).date().isoformat()
    assert stats["trend"][-1]["date"] == today
    assert sum(stats["trend"][-1][k] for k in VERDICTS) == 2
    assert all(sum(t[k] for k in VERDICTS) == 0 for t in stats["trend"][:-1])
    assert len(stats["recent"]) == 2
    assert 0 <= stats["avg_authenticity_score"] <= 100

    # report PDF (generated, then cached)
    r = client.get(f"{a['report_url']}?token={token}")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    r2 = client.get(a["report_url"], headers=h)
    assert r2.status_code == 200 and r2.content.startswith(b"%PDF")


def test_dashboard_empty(client, token):
    s = client.get("/api/dashboard/stats", headers=auth_headers(token)).json()
    assert s["total_images"] == 0 and s["total_analyses"] == 0 and s["avg_authenticity_score"] == 0
    assert len(s["trend"]) == 7 and s["recent"] == []


def test_restore_boxes_mask_and_report(client, token):
    h = auth_headers(token)
    img = upload(client, token, make_png((100, 80))).json()
    a = _analyze(client, token, img["id"])

    r = client.post(f"/api/analyses/{a['id']}/restore", json={"boxes": [[10, 10, 20, 20]]}, headers=h)
    assert r.status_code == 201, r.text
    rest = r.json()
    assert set(rest) == {"id", "analysis_id", "method", "note", "created_at", "url"}
    assert rest["url"] == f"/api/restorations/{rest['id']}/file"
    f = client.get(f"{rest['url']}?token={token}")
    assert f.status_code == 200 and f.headers["content-type"] == "image/png"

    mask = PILImage.new("RGBA", (100, 80), (0, 0, 0, 0))
    for x in range(30, 50):
        for y in range(30, 50):
            mask.putpixel((x, y), (255, 255, 255, 255))
    buf = io.BytesIO()
    mask.save(buf, "PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    r = client.post(f"/api/analyses/{a['id']}/restore", json={"mask_base64": data_url}, headers=h)
    assert r.status_code == 201, r.text

    r = client.post(f"/api/analyses/{a['id']}/restore", json={}, headers=h)
    assert r.status_code == 201, r.text

    bad = client.post(f"/api/analyses/{a['id']}/restore", json={"mask_base64": "data:image/png;base64,!!!"},
                      headers=h)
    assert bad.status_code == 400
    bad = client.post(f"/api/analyses/{a['id']}/restore", json={"boxes": [[1, 2, 3]]}, headers=h)
    assert bad.status_code == 422

    got = client.get(f"/api/analyses/{a['id']}", headers=h).json()
    assert len(got["restorations"]) == 3

    pdf = client.get(f"/api/reports/{a['id']}/pdf", headers=h)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    # deleting the image cascades to analyses/restorations
    assert client.delete(f"/api/images/{img['id']}", headers=h).status_code == 204
    assert client.get(f"/api/analyses/{a['id']}", headers=h).status_code == 404
    assert client.get(rest["url"], headers=h).status_code == 404


def test_pipeline_failure_returns_500_without_row(client, token, monkeypatch):
    from app.services import ml

    def boom(*_a, **_k):
        raise RuntimeError("model exploded")

    monkeypatch.setattr(ml, "analyze_image", boom)
    h = auth_headers(token)
    img = upload(client, token).json()
    r = client.post("/api/analyses", json={"image_id": img["id"]}, headers=h)
    assert r.status_code == 500
    assert "model exploded" in r.json()["detail"]
    assert client.get("/api/history", headers=h).json()["total"] == 0
