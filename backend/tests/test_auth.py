from tl_helpers import auth_headers, register


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["ml_deep_enabled"] is False
    assert isinstance(body["models_loaded"], bool)


def test_register_login_me(client):
    reg = register(client, email="Bob@Example.com", name="Bob")
    assert reg["token_type"] == "bearer"
    assert reg["access_token"]
    assert reg["user"]["email"] == "bob@example.com"
    assert set(reg["user"]) == {"id", "name", "email", "created_at"}
    assert reg["user"]["created_at"].endswith("Z")

    r = client.post("/api/auth/login", json={"email": "bob@example.com", "password": "password123"})
    assert r.status_code == 200
    tok = r.json()["access_token"]

    me = client.get("/api/auth/me", headers=auth_headers(tok))
    assert me.status_code == 200
    assert me.json()["name"] == "Bob"


def test_duplicate_email(client):
    register(client)
    r = client.post("/api/auth/register",
                    json={"name": "X", "email": "ALICE@example.com", "password": "password123"})
    assert r.status_code == 409
    assert isinstance(r.json()["detail"], str)


def test_bad_password(client):
    register(client)
    r = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "wrongpass1"})
    assert r.status_code == 401
    assert r.json()["detail"]
    r = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "password123"})
    assert r.status_code == 401


def test_validation_errors_are_strings(client):
    r = client.post("/api/auth/register", json={"name": "A", "email": "not-an-email", "password": "short"})
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str)


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers=auth_headers("garbage")).status_code == 401
