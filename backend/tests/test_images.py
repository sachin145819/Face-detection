import os

from tl_helpers import auth_headers, make_png, upload


def test_upload_png_ok(client, token):
    r = upload(client, token)
    assert r.status_code == 201, r.text
    img = r.json()
    assert img["mime_type"] == "image/png"
    assert (img["width"], img["height"]) == (64, 48)
    assert img["url"] == f"/api/images/{img['id']}/file"
    assert img["original_filename"] == "photo.png"
    assert set(img) == {"id", "original_filename", "mime_type", "size_bytes", "width", "height",
                        "uploaded_at", "url"}

    # file via bearer and via ?token=
    f = client.get(img["url"], headers=auth_headers(token))
    assert f.status_code == 200 and f.headers["content-type"] == "image/png"
    f = client.get(f"{img['url']}?token={token}")
    assert f.status_code == 200
    assert client.get(img["url"]).status_code == 401

    lst = client.get("/api/images", headers=auth_headers(token)).json()
    assert [i["id"] for i in lst] == [img["id"]]


def test_upload_jpeg_and_webp(client, token):
    r = upload(client, token, make_png(fmt="JPEG"), "a.jpg", "image/jpeg")
    assert r.status_code == 201 and r.json()["mime_type"] == "image/jpeg"
    r = upload(client, token, make_png(fmt="WEBP"), "a.webp", "image/webp")
    assert r.status_code == 201 and r.json()["mime_type"] == "image/webp"


def test_upload_rejects_fake_image(client, token):
    r = upload(client, token, b"this is not an image at all", "evil.png", "image/png")
    assert r.status_code == 400
    assert isinstance(r.json()["detail"], str)


def test_upload_rejects_other_format(client, token):
    r = upload(client, token, make_png(fmt="GIF"), "anim.gif", "image/gif")
    assert r.status_code == 400
    r = upload(client, token, make_png(fmt="GIF"), "sneaky.png", "image/png")
    assert r.status_code == 400


def test_upload_too_large(client, token, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    big = os.urandom(1024 * 1024 + 10)
    r = upload(client, token, big, "big.png", "image/png")
    assert r.status_code == 413


def test_upload_requires_auth(client):
    r = client.post("/api/images", files={"file": ("a.png", make_png(), "image/png")})
    assert r.status_code == 401


def test_delete_image(client, token):
    img = upload(client, token).json()
    r = client.delete(f"/api/images/{img['id']}", headers=auth_headers(token))
    assert r.status_code == 204
    assert client.get(f"/api/images/{img['id']}", headers=auth_headers(token)).status_code == 404
