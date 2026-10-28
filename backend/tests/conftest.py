"""Backend test fixtures: temp SQLite DB + temp STORAGE_DIR per test, ML deep models off."""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Must happen before any `app` import so settings/engine pick these up.
_SESSION_TMP = tempfile.mkdtemp(prefix="truthlens-tests-")
atexit.register(shutil.rmtree, _SESSION_TMP, ignore_errors=True)
os.environ["DATABASE_URL"] = f"sqlite:///{_SESSION_TMP}/session.db"
os.environ["STORAGE_DIR"] = f"{_SESSION_TMP}/storage"
os.environ["ML_ENABLE_DEEP"] = "false"
os.environ["SECRET_KEY"] = "test-secret"
os.environ.setdefault("MAX_UPLOAD_MB", "10")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database import Base, get_db, make_engine  # noqa: E402
from app.main import app  # noqa: E402
from tl_helpers import register  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    storage_dir = tmp_path / "storage"
    monkeypatch.setenv("STORAGE_DIR", str(storage_dir))
    get_settings.cache_clear()

    engine = make_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    engine.dispose()
    get_settings.cache_clear()


@pytest.fixture()
def user(client):
    return register(client)


@pytest.fixture()
def token(user):
    return user["access_token"]
