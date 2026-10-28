#!/bin/sh
# TruthLens backend entrypoint:
#   1. wait for the database (PostgreSQL only; SQLite needs no wait)
#   2. run Alembic migrations
#   3. exec uvicorn (or any command passed to the container)
set -eu

cd /app

DB_WAIT_TIMEOUT="${DB_WAIT_TIMEOUT:-60}"
RUN_MIGRATIONS="${RUN_MIGRATIONS:-true}"
UVICORN_WORKERS="${UVICORN_WORKERS:-1}"
PORT="${PORT:-8000}"

mkdir -p "${STORAGE_DIR:-/app/storage}" "${MODEL_CACHE_DIR:-/app/models_cache}"

case "${DATABASE_URL:-}" in
  postgres*)
    echo "[entrypoint] Waiting for PostgreSQL (timeout ${DB_WAIT_TIMEOUT}s)..."
    python - <<'PY'
import os, sys, time
from sqlalchemy import create_engine, text

url = os.environ["DATABASE_URL"]
# Render/Heroku style URLs -> SQLAlchemy + psycopg v3 driver (mirrors app/database.py).
if url.startswith("postgres://"):
    url = "postgresql://" + url[len("postgres://"):]
if url.startswith("postgresql://"):
    url = "postgresql+psycopg://" + url[len("postgresql://"):]
deadline = time.monotonic() + int(os.environ.get("DB_WAIT_TIMEOUT", "60"))
engine = create_engine(url, pool_pre_ping=True)
last_err = None
while time.monotonic() < deadline:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("[entrypoint] PostgreSQL is ready.")
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        last_err = exc
        time.sleep(1.5)
print(f"[entrypoint] ERROR: database not reachable: {last_err}", file=sys.stderr)
sys.exit(1)
PY
    ;;
  *)
    echo "[entrypoint] Non-PostgreSQL DATABASE_URL; skipping DB wait."
    ;;
esac

if [ "${RUN_MIGRATIONS}" = "true" ]; then
  if [ -f alembic.ini ]; then
    echo "[entrypoint] Running database migrations (alembic upgrade head)..."
    alembic upgrade head
  else
    echo "[entrypoint] WARNING: alembic.ini not found; skipping migrations."
  fi
fi

# Allow `docker run image <cmd>` (e.g. `pytest`, `bash`) to override the server.
if [ "$#" -gt 0 ]; then
  exec "$@"
fi

echo "[entrypoint] Starting uvicorn on :${PORT} with ${UVICORN_WORKERS} worker(s)."
echo "[entrypoint] Note: ML models are loaded per worker process (RAM scales with workers)."
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --workers "${UVICORN_WORKERS}" \
  --proxy-headers \
  --forwarded-allow-ips='*' \
  --timeout-keep-alive 75
