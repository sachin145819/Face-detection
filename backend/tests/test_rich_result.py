"""Exercise heatmap/ELA relocation and the full PDF layout with a rich fake pipeline result."""
import os
from pathlib import Path

from PIL import Image as PILImage

from tl_helpers import auth_headers, make_png, upload


def fake_analyze(image_path: str, output_dir: str) -> dict:
    with PILImage.open(image_path) as im:
        w, h = im.size
        heat = im.convert("RGB")
    heat.save(os.path.join(output_dir, "heatmap.png"))
    PILImage.new("RGB", (w, h), (30, 30, 30)).save(os.path.join(output_dir, "ela.png"))
    return {
        "verdict": "deepfake",
        "authenticity_score": 12.5,
        "confidence": 0.83,
        "uncertainty_note": "Face model and noise analysis disagree; ELA weak on PNG.",
        "summary": "A face shows strong deepfake artefacts.",
        "signals": [
            {"key": k, "label": k.title(), "score": 0.1 * i, "weight": 0.2, "available": i % 2 == 0,
             "explanation": "x" * 400, "details": {"a": 1}}
            for i, k in enumerate(("metadata", "ela", "noise", "frequency", "deepfake", "ai_generated"))
        ],
        "faces": [{"box": [5, 5, 20, 20], "deepfake_probability": 0.91}],
        "regions": [{"box": [10, 10, 30, 15], "score": 0.7, "source": "ela"}],
        "metadata": {"format": "PNG", "width": w, "height": h, "software": "GIMP",
                     "exif": {"Make": "Canon", "MakerNote": "Z" * 5000, "Unicode": "日本語 ✓"}},
        "heatmap_path": os.path.join(output_dir, "heatmap.png"),
        "ela_path": os.path.join(output_dir, "ela.png"),
        "processing_ms": 42,
        "model_versions": {"deepfake": "fake-v1", "ai_generated": None},
    }


def test_rich_result_heatmap_ela_and_report(client, token, monkeypatch):
    from app.services import ml

    monkeypatch.setattr(ml, "analyze_image", fake_analyze)
    h = auth_headers(token)
    img = upload(client, token, make_png((160, 120))).json()
    r = client.post("/api/analyses", json={"image_id": img["id"]}, headers=h)
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["verdict"] == "deepfake"
    assert a["heatmap_url"] == f"/api/analyses/{a['id']}/heatmap"
    assert a["ela_url"] == f"/api/analyses/{a['id']}/ela"
    assert "heatmap_path" not in a["result"]
    assert client.get(a["heatmap_url"], headers=h).status_code == 200
    assert client.get(f"{a['ela_url']}?token={token}").status_code == 200

    # files were moved into analyses/<id>/ and no tmp dirs remain
    storage = Path(os.environ["STORAGE_DIR"])
    assert (storage / "analyses" / str(a["id"]) / "heatmap.png").is_file()
    assert not [p for p in (storage / "analyses").iterdir() if p.name.startswith("tmp-")]

    client.post(f"/api/analyses/{a['id']}/restore", json={"boxes": [[10, 10, 30, 15]]}, headers=h)
    pdf = client.get(a["report_url"], headers=h)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert len(pdf.content) > 5000
