# TruthLens — Deployment Guide

There are two supported options:

1. **Single VPS with Docker Compose**: the simplest option, and everything stays on one host.
2. **Split deployment**: the frontend on Vercel and the backend (plus managed Postgres) on Render or
   Railway.

---

## Option A — Docker Compose on a VPS

### Requirements

| Resource | Minimum | Recommended |
|---|---|---|
| RAM | 2 GB (`ML_ENABLE_DEEP=false`) | **≥ 4 GB** with the deep models (each Uvicorn worker loads its own copy) |
| CPU | 1 vCPU | 2+ vCPU (an analysis takes about 15 s on CPU) |
| Disk | 10 GB | 20 GB (images ~3–4 GB with CPU torch + weights, plus uploads) |
| OS | Any Linux with Docker Engine 24+ and the Compose v2 plugin | Ubuntu 22.04/24.04 LTS |

No GPU is needed. The images use CPU-only PyTorch wheels.

### Steps

```bash
# 1. Install Docker (Ubuntu)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER" && newgrp docker

# 2. Get the code
git clone <your-repo-url> truthlens && cd truthlens

# 3. Configure
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # paste into SECRET_KEY
nano .env      # set SECRET_KEY, POSTGRES_PASSWORD, CORS_ORIGINS=https://your.domain

# 4. Build and start
docker compose up -d --build
docker compose ps            # all services should become "healthy"
docker compose logs -f backend
```

The app is now available on `http://<server-ip>:8080`. Change `FRONTEND_PORT=80` in `.env` to serve it on
port 80.

### HTTPS

Put a TLS-terminating reverse proxy in front of the `frontend` service. The simplest option is
[Caddy](https://caddyserver.com/), which gets certificates automatically:

```
# /etc/caddy/Caddyfile
truthlens.example.com {
    reverse_proxy 127.0.0.1:8080
    request_body {
        max_size 12MB
    }
}
```

### Operations

| Task | Command |
|---|---|
| Update to the latest code | `git pull && docker compose up -d --build` |
| View logs | `docker compose logs -f --tail=200` |
| Run migrations manually | `docker compose exec backend alembic upgrade head` |
| Open a DB shell | `docker compose exec db psql -U truthlens truthlens` |
| Back up the DB | `docker compose exec -T db pg_dump -U truthlens truthlens > backup.sql` |
| Back up uploads/reports | `docker run --rm -v truthlens_storage:/d -v "$PWD":/b alpine tar czf /b/storage.tgz -C /d .` |
| Faster builds (no baked weights) | `PRELOAD_MODELS=false docker compose build backend` |
| Classical-only mode (low RAM) | set `ML_ENABLE_DEEP=false` in `.env`, then `docker compose up -d` |

Migrations run automatically on every backend start (`RUN_MIGRATIONS=true`).

---

## Option B — Split: Vercel (frontend) + Render/Railway (backend)

```
Browser ──► Vercel (static SPA) ──rewrite /api/*──► Render/Railway backend ──► managed PostgreSQL
```

Because the SPA always calls **relative** `/api/...` URLs, a Vercel rewrite keeps the browser on the same
origin. No CORS or frontend code changes are needed.

### B1. Backend on Render (Docker)

1. **New → PostgreSQL** (any plan). Copy the *Internal Database URL*.
2. **New → Web Service**, then connect the repository.
   - Runtime: **Docker**. Root directory: `backend` (Dockerfile path `backend/Dockerfile`).
   - Instance: at least **2 GB RAM** for the deep models (Starter plans: use `ML_ENABLE_DEEP=false`).
   - Health check path: `/api/health`.
   - Add a **persistent disk** mounted at `/app/storage` (uploads, heatmaps, reports). Without one, files
     are lost on every deploy.
3. Environment variables:

| Var | Value |
|---|---|
| `DATABASE_URL` | Render's Postgres URL (`postgres://…` is accepted and normalised to `postgresql+psycopg://`) |
| `SECRET_KEY` | long random string |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` |
| `STORAGE_DIR` | `/app/storage` |
| `MODEL_CACHE_DIR` | `/app/models_cache` |
| `CORS_ORIGINS` | `https://<your-app>.vercel.app` |
| `MAX_UPLOAD_MB` | `10` |
| `ML_ENABLE_DEEP` | `true` (or `false` on small instances) |
| `UVICORN_WORKERS` | `1` |
| `PORT` | set by Render automatically; the entrypoint honours it |

Docker build arg `PRELOAD_MODELS` defaults to `true`, so the weights are baked into the image and cold starts
avoid a download.

### B1'. Backend on Railway

Create the service from the repo with root directory `backend` (Railway detects the Dockerfile) and add the
**PostgreSQL** plugin. Set `DATABASE_URL=${{Postgres.DATABASE_URL}}` plus the same variables as above. Attach
a **volume** at `/app/storage`. Railway injects `PORT`, which the entrypoint uses.

### B2. Frontend on Vercel

1. **Import project**, then set Root Directory to `frontend`. Framework preset: **Vite** (build
   `npm run build`, output `dist`).
2. Add `frontend/vercel.json` (owned by the frontend team; create it at deploy time) so that `/api` is
   proxied to the backend and client-side routes fall back to `index.html`:

```json
{
  "rewrites": [
    { "source": "/api/:path*", "destination": "https://<your-backend>.onrender.com/api/:path*" },
    { "source": "/((?!assets/).*)", "destination": "/index.html" }
  ]
}
```

3. No frontend environment variables are needed, because the API base is the relative `/api`.

> **Timeouts:** Vercel rewrites to external origins have a limited proxy timeout. If the first analysis
> (model warm-up) times out, call `GET /api/health` once after each deploy to warm the backend, or keep the
> backend on an always-on plan.

### Smoke test

```bash
curl -s https://<backend>/api/health
# {"status":"ok","ml_deep_enabled":true,"models_loaded":true}
curl -s https://<frontend>/api/health     # same response via the proxy/rewrite
```

---

## Environment variable reference

| Var | Used by | Default | Notes |
|---|---|---|---|
| `DATABASE_URL` | backend | `sqlite:///./truthlens.db` | Compose builds it from `POSTGRES_*` |
| `SECRET_KEY` | backend | `dev-secret-change-me` | **change in production** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | backend | `1440` | |
| `STORAGE_DIR` | backend | `./storage` (`/app/storage` in Docker) | persist it |
| `CORS_ORIGINS` | backend | `http://localhost:5173` | comma-separated |
| `MAX_UPLOAD_MB` | backend | `10` | nginx allows 12 MB bodies |
| `ML_ENABLE_DEEP` | backend | `true` | `false` = classical forensics only |
| `MODEL_CACHE_DIR` | backend | `./models_cache` (`/app/models_cache` in Docker) | |
| `UVICORN_WORKERS` | backend container | `1` | RAM grows with each worker |
| `RUN_MIGRATIONS` | backend container | `true` | `alembic upgrade head` on start |
| `DB_WAIT_TIMEOUT` | backend container | `60` | seconds to wait for Postgres |
| `PORT` | backend container | `8000` | |
| `PRELOAD_MODELS` | backend build arg | `true` | bake model weights into the image |
| `BACKEND_UPSTREAM` | frontend container | `backend:8000` | where nginx proxies `/api` |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | compose `db` | `truthlens` | |
| `FRONTEND_PORT` / `BACKEND_PORT` / `POSTGRES_PORT` | compose | `8080` / `8000` / `5432` | host ports |
