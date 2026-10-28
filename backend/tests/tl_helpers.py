"""Shared helpers for backend tests."""
import io

from PIL import Image as PILImage


def make_png(size=(64, 48), color=(200, 30, 30), fmt="PNG") -> bytes:
    img = PILImage.new("RGB", size, color)
    # a little structure so forensic algorithms have something to chew on
    for x in range(0, size[0], 8):
        for y in range(size[1]):
            img.putpixel((x, y), (20, 20, 20))
    buf = io.BytesIO()
    img.save(buf, fmt)
    return buf.getvalue()


def register(client, email="alice@example.com", password="password123", name="Alice"):
    r = client.post("/api/auth/register", json={"name": name, "email": email, "password": password})
    assert r.status_code == 201, r.text
    return r.json()


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def upload(client, token, data=None, filename="photo.png", mime="image/png"):
    data = data if data is not None else make_png()
    return client.post("/api/images", files={"file": (filename, data, mime)}, headers=auth_headers(token))
