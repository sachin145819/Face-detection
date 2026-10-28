from tl_helpers import auth_headers, register, upload


def test_users_cannot_access_each_others_resources(client):
    alice = register(client, email="alice@example.com")["access_token"]
    bob = register(client, email="bob@example.com", name="Bob")["access_token"]
    ha, hb = auth_headers(alice), auth_headers(bob)

    img = upload(client, alice).json()
    a = client.post("/api/analyses", json={"image_id": img["id"]}, headers=ha).json()
    rest = client.post(f"/api/analyses/{a['id']}/restore", json={"boxes": [[1, 1, 5, 5]]}, headers=ha).json()

    # Bob sees nothing and gets 404 on everything of Alice's
    assert client.get("/api/images", headers=hb).json() == []
    assert client.get(f"/api/images/{img['id']}", headers=hb).status_code == 404
    assert client.get(f"/api/images/{img['id']}/file?token={bob}").status_code == 404
    assert client.delete(f"/api/images/{img['id']}", headers=hb).status_code == 404
    assert client.post("/api/analyses", json={"image_id": img["id"]}, headers=hb).status_code == 404
    assert client.get(f"/api/analyses/{a['id']}", headers=hb).status_code == 404
    assert client.get(f"/api/analyses/{a['id']}/heatmap", headers=hb).status_code == 404
    assert client.get(f"/api/analyses/{a['id']}/ela", headers=hb).status_code == 404
    assert client.post(f"/api/analyses/{a['id']}/restore", json={}, headers=hb).status_code == 404
    assert client.get(f"/api/restorations/{rest['id']}/file?token={bob}").status_code == 404
    assert client.get(f"/api/reports/{a['id']}/pdf?token={bob}").status_code == 404
    assert client.get("/api/history", headers=hb).json()["total"] == 0
    stats = client.get("/api/dashboard/stats", headers=hb).json()
    assert stats["total_images"] == 0 and stats["total_analyses"] == 0

    # Alice still has access
    assert client.get(f"/api/images/{img['id']}", headers=ha).status_code == 200
    assert client.get(f"/api/analyses/{a['id']}", headers=ha).status_code == 200
