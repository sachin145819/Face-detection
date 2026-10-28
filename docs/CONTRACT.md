# TruthLens — Shared Build Contract

This file is the single source of truth that every part of the system (frontend, backend, database,
AI/ML, DevOps) builds against. If you need to change it, keep changes backward compatible and note them
at the bottom under "Changelog".

TruthLens = AI-Based Image Authenticity Verification, Deepfake Detection & Intelligent Content
Restoration System (GL Bajaj mini project). A signed-in user uploads an image (JPEG/PNG/WebP), gets a
verdict (authentic / manipulated / deepfake / ai_generated) with a 0–100 authenticity score, an
explainability heatmap, suspicious-region boxes, optional AI restoration (clearly labelled), a PDF
forensic report, per-user history and a dashboard. Verdicts are probabilistic evidence, never certainty.

## 1. Repository layout and ownership

```
Chill-Fun-Hacakthon/
├── backend/                     # Python 3.11+ FastAPI app
│   ├── app/
│   │   ├── main.py              # BACKEND
│   │   ├── config.py            # BACKEND
│   │   ├── database.py          # BACKEND
│   │   ├── models/              # BACKEND (SQLAlchemy tables)
│   │   ├── schemas/             # BACKEND (Pydantic)
│   │   ├── routes/              # BACKEND
│   │   ├── services/            # BACKEND (incl. PDF report generation)
│   │   └── ml/                  # ML  (pipeline.py is the ONLY entry point backend imports)
│   ├── alembic/ + alembic.ini   # BACKEND
│   ├── tests/                   # BACKEND (except tests/ml/)
│   ├── tests/ml/                # ML
│   ├── scripts/download_models.py  # ML
│   ├── requirements.txt         # BACKEND (must contain the line `-r requirements-ml.txt`)
│   ├── requirements-ml.txt      # ML
│   └── Dockerfile               # DEVOPS
├── frontend/                    # React 18 + Vite + Tailwind  — FRONTEND
│   ├── Dockerfile               # DEVOPS
│   └── nginx.conf               # DEVOPS
├── docker-compose.yml           # DEVOPS
├── .github/workflows/           # DEVOPS
├── Makefile, .env.example, .gitignore, README.md   # DEVOPS
└── docs/CONTRACT.md             # shared (this file)
```

Never edit files owned by another part. Do not run `git commit`.

## 2. Runtime configuration (environment variables, read by backend/app/config.py)

| Var | Default (local dev) | Notes |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./truthlens.db` | Compose uses `postgresql+psycopg://truthlens:truthlens@db:5432/truthlens` |
| `SECRET_KEY` | `dev-secret-change-me` | JWT signing key |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | |
| `STORAGE_DIR` | `./storage` | subdirs: `uploads/`, `analyses/<id>/`, `restored/`, `reports/` |
| `CORS_ORIGINS` | `http://localhost:5173` | comma-separated |
| `MAX_UPLOAD_MB` | `10` | |
| `ML_ENABLE_DEEP` | `true` | `false` → pipeline uses classical forensics only (fast, no torch) |
| `MODEL_CACHE_DIR` | `./models_cache` | HF / torch weights cache |

Local dev: backend at `http://localhost:8000`, frontend (Vite) at `http://localhost:5173` with a dev proxy
`/api → http://localhost:8000`. Production (compose): nginx in the frontend container serves the SPA on
port 80 and proxies `/api` to `backend:8000`. So the frontend ALWAYS calls relative `/api/...` URLs.

Python virtualenv for local dev: `backend/.venv` (create with `uv venv backend/.venv --python 3.12`).

## 3. Database schema (SQLAlchemy 2.0, Alembic migrations)

- `users`: id PK, name, email UNIQUE, password_hash, created_at
- `images`: id PK, user_id FK→users (cascade), original_filename, stored_filename (uuid), mime_type,
  size_bytes, width, height, sha256, uploaded_at
- `analyses`: id PK, image_id FK→images (cascade), user_id FK→users, verdict (str), authenticity_score
  (float 0–100), confidence (float 0–1), result_json (JSON — the full `analyze_image` result), heatmap_path,
  ela_path, processing_ms, created_at
- `restorations`: id PK, analysis_id FK→analyses (cascade), user_id, method, note, restored_path, created_at
- `reports`: id PK, analysis_id FK→analyses UNIQUE (cascade), pdf_path, created_at

Must work on both SQLite and PostgreSQL (use `sqlalchemy.JSON`, not JSONB).

## 4. ML interface (backend/app/ml/pipeline.py)

The backend imports ONLY these two functions. Both are synchronous; backend runs them in a threadpool.

```python
def analyze_image(image_path: str, output_dir: str) -> dict: ...
def restore_image(image_path: str, output_path: str,
                  boxes: list[list[int]] | None = None,
                  mask_path: str | None = None) -> dict: ...
def warmup() -> None: ...   # optional: preload models; backend calls it at startup in a background thread
```

`analyze_image` returns (all keys always present):

```json
{
  "verdict": "authentic | manipulated | deepfake | ai_generated",
  "authenticity_score": 0-100,          // 100 = definitely authentic
  "confidence": 0.0-1.0,                // confidence in the verdict label
  "uncertainty_note": "string, human readable, explains disagreement / limits",
  "summary": "one or two plain-English sentences explaining the verdict",
  "signals": [
    {"key": "ela", "label": "Error Level Analysis", "score": 0.0-1.0,   // suspicion: 1 = suspicious
     "weight": 0.15, "available": true, "explanation": "string", "details": {}}
  ],
  "faces":   [{"box": [x, y, w, h], "deepfake_probability": 0.0-1.0}],
  "regions": [{"box": [x, y, w, h], "score": 0.0-1.0, "source": "ela | noise | deepfake | gradcam"}],
  "metadata": {"format": "JPEG", "width": 0, "height": 0, "exif": {"Make": "..."}, "software": null},
  "heatmap_path": "/abs/path/in/output_dir/heatmap.png or null",   // heatmap overlaid on image
  "ela_path": "/abs/path/in/output_dir/ela.png or null",
  "processing_ms": 0,
  "model_versions": {"deepfake": "name or null", "ai_generated": "name or null"}
}
```

Signal keys (at minimum): `metadata`, `ela`, `noise`, `frequency`, `deepfake`, `ai_generated`. A signal whose
model is unavailable has `"available": false` and is excluded from weighting. All numbers JSON-serialisable
(no numpy types). Coordinates are in original image pixels.

`restore_image` writes a PNG to `output_path` and returns
`{"restored_path": str, "method": "opencv_telea | lama | ...", "note": "AI-reconstructed region — not original evidence"}`.
If neither boxes nor mask is given it uses the regions from a fresh analysis (or the top suspicious area).
The output image must carry a visible "AI-RECONSTRUCTED" label.

## 5. REST API (prefix `/api`, JSON, errors as `{"detail": "message"}`)

Auth: `Authorization: Bearer <jwt>`. Endpoints that return binary files (marked 📎) ALSO accept
`?token=<jwt>` so the frontend can use them directly in `<img src>` / `<a href>`.
All file URLs returned by the API are relative (e.g. `/api/images/3/file`); the frontend appends `?token=`.

| Method | Path | Body / Query | Response |
|---|---|---|---|
| GET | `/api/health` | – | `{"status":"ok","ml_deep_enabled":bool,"models_loaded":bool}` |
| POST | `/api/auth/register` | `{name,email,password}` (password ≥ 8) | `TokenOut` (201) |
| POST | `/api/auth/login` | `{email,password}` | `TokenOut` |
| GET | `/api/auth/me` | – | `UserOut` |
| POST | `/api/images` | multipart, field `file` | `ImageOut` (201); 400 bad type, 413 too large |
| GET | `/api/images` | – | `ImageOut[]` (newest first) |
| GET | `/api/images/{id}` | – | `ImageOut` |
| GET 📎 | `/api/images/{id}/file` | – | original image bytes |
| DELETE | `/api/images/{id}` | – | 204 (deletes files + analyses) |
| POST | `/api/analyses` | `{image_id}` | `AnalysisOut` (201) — runs pipeline synchronously |
| GET | `/api/analyses/{id}` | – | `AnalysisOut` |
| GET 📎 | `/api/analyses/{id}/heatmap` | – | PNG (404 if none) |
| GET 📎 | `/api/analyses/{id}/ela` | – | PNG (404 if none) |
| POST | `/api/analyses/{id}/restore` | `{boxes?: [[x,y,w,h]], mask_base64?: "data:image/png;base64,..."}` | `RestorationOut` (201) |
| GET 📎 | `/api/restorations/{id}/file` | – | PNG |
| GET 📎 | `/api/reports/{analysis_id}/pdf` | – | PDF (generated on first request, cached) |
| GET | `/api/history` | `q` (filename search), `verdict`, `page`=1, `page_size`=10 | `{items: HistoryItem[], total, page, page_size}` |
| GET | `/api/dashboard/stats` | – | `DashboardStats` |

Users can only ever access their own images/analyses/restorations/reports (404 otherwise).

Schemas:

```ts
TokenOut       = { access_token: string, token_type: "bearer", user: UserOut }
UserOut        = { id: number, name: string, email: string, created_at: string }
ImageOut       = { id, original_filename, mime_type, size_bytes, width, height, uploaded_at, url /* /api/images/{id}/file */ }
AnalysisOut    = { id, image_id, verdict, authenticity_score, confidence, created_at, processing_ms,
                   result /* full analyze_image dict, with heatmap_path/ela_path REMOVED */,
                   image: ImageOut,
                   heatmap_url: string|null, ela_url: string|null, report_url /* /api/reports/{id}/pdf */,
                   restorations: RestorationOut[] }
RestorationOut = { id, analysis_id, method, note, created_at, url /* /api/restorations/{id}/file */ }
HistoryItem    = { analysis_id, image_id, original_filename, verdict, authenticity_score, confidence,
                   created_at, thumbnail_url /* image url */ }
DashboardStats = { total_images, total_analyses, avg_authenticity_score,
                   by_verdict: { authentic, manipulated, deepfake, ai_generated },
                   trend: [{ date: "YYYY-MM-DD", authentic, manipulated, deepfake, ai_generated }] /* last 7 days incl. today, zero-filled */,
                   recent: HistoryItem[] /* last 5 */ }
```

Datetimes are ISO-8601 strings (UTC).

## 6. Video analysis (v2)

Users can also upload a short video (MP4 / MOV / WebM / AVI / MKV, ≤ `MAX_VIDEO_MB`, default 100) and get
a deepfake / AI-generated verdict with a per-frame suspicion timeline and the most suspicious frames.
Classical image forensics (ELA, noise) are NOT run on video frames — video codecs destroy those traces.

### 6.1 New env vars
| Var | Default | Notes |
|---|---|---|
| `MAX_VIDEO_MB` | `100` | upload cap for videos (413 above it) |
| `VIDEO_MAX_FRAMES` | `16` | frames sampled evenly across the video for analysis |

### 6.2 ML interface (added to backend/app/ml/pipeline.py — still the only module the backend imports)

```python
def probe_video(video_path: str) -> dict: ...
    # -> {"duration_s": float, "fps": float, "frame_count": int, "width": int, "height": int,
    #     "codec": str|None, "format": str|None}
    # raises ValueError if the file is not a decodable video (backend maps that to 400)

def analyze_video(video_path: str, output_dir: str, max_frames: int | None = None) -> dict: ...
```

`analyze_video` writes JPEG/PNG files into `output_dir` and returns (all keys always present):

```json
{
  "media_type": "video",
  "verdict": "authentic | manipulated | deepfake | ai_generated",
  "authenticity_score": 0-100,
  "confidence": 0.0-1.0,
  "summary": "plain-English explanation",
  "uncertainty_note": "string",
  "signals": [   // same shape as image signals; keys: "deepfake", "ai_generated", "temporal", "metadata"
    {"key": "deepfake", "label": "Face deepfake (across frames)", "score": 0.0-1.0, "weight": 0.0-1.0,
     "available": true, "explanation": "string", "details": {}}
  ],
  "video": {"duration_s": 0.0, "fps": 0.0, "frame_count": 0, "width": 0, "height": 0,
            "codec": "h264 or null", "format": "mp4 or null"},
  "frames": [    // sampled frames, ordered by time
    {"index": 0, "timestamp_s": 0.0,
     "suspicion": 0.0-1.0,                       // fused per-frame suspicion
     "deepfake_probability": 0.0-1.0 | null,     // max over analysed faces; null = no face analysed
     "ai_generated_probability": 0.0-1.0 | null, // null = model unavailable
     "faces": [{"box": [x, y, w, h], "deepfake_probability": 0.0-1.0 | null}],
     "thumbnail_path": "/abs/path/in/output_dir/frame_000.jpg",
     "heatmap_path": "/abs/path/in/output_dir/frame_000_heat.jpg or null"}
  ],
  "top_frames": [3, 7],          // indices into `frames`, most suspicious first, at most 4
  "faces_detected_frames": 0,    // how many sampled frames contained at least one face
  "metadata": {"encoder": "string or null", "generator_hint": "Sora | Runway | ... | null", "tags": {}},
  "processing_ms": 0,
  "model_versions": {"deepfake": "id or null", "ai_generated": "id or null"}
}
```

Box coordinates are in the video's display pixel space (`video.width` × `video.height`). All values are plain
JSON types. Thumbnails are ≤ 640 px on the long side.

### 6.3 Database (new tables, new Alembic migration)
- `videos`: id PK, user_id FK→users (cascade), original_filename, stored_filename, mime_type, size_bytes,
  width, height, duration_s (float), fps (float), frame_count, sha256, uploaded_at
- `video_analyses`: id PK, video_id FK→videos (cascade), user_id FK→users, verdict, authenticity_score,
  confidence, result_json (JSON), processing_ms, report_path (nullable), created_at
- Storage: `STORAGE_DIR/videos/<uuid>.<ext>` and `STORAGE_DIR/video_analyses/<id>/`.

### 6.4 REST API additions

| Method | Path | Body / Query | Response |
|---|---|---|---|
| POST | `/api/videos` | multipart, field `file` | `VideoOut` (201); 400 bad type/undecodable, 413 too large |
| GET | `/api/videos` | – | `VideoOut[]` newest first |
| GET | `/api/videos/{id}` | – | `VideoOut` |
| GET 📎 | `/api/videos/{id}/file` | – | video bytes; MUST support HTTP Range (seeking in `<video>`) |
| DELETE | `/api/videos/{id}` | – | 204 (deletes files + analyses) |
| POST | `/api/video-analyses` | `{video_id}` | `VideoAnalysisOut` (201) — runs synchronously |
| GET | `/api/video-analyses/{id}` | – | `VideoAnalysisOut` |
| GET 📎 | `/api/video-analyses/{id}/files/{name}` | – | a frame thumbnail / heatmap written by the pipeline (basename only; anything else → 404) |
| GET 📎 | `/api/video-analyses/{id}/report` | – | PDF video forensic report (generated on first request, cached) |

```ts
VideoOut         = { id, original_filename, mime_type, size_bytes, width, height, duration_s, fps,
                     frame_count, uploaded_at, url /* /api/videos/{id}/file */ }
VideoAnalysisOut = { id, video_id, verdict, authenticity_score, confidence, created_at, processing_ms,
                     result /* analyze_video dict; every frames[].thumbnail_path / heatmap_path is REMOVED and
                               replaced by thumbnail_url / heatmap_url (/api/video-analyses/{id}/files/<basename>, or null) */,
                     video: VideoOut, report_url /* /api/video-analyses/{id}/report */ }
```

### 6.5 Changes to existing endpoints (backward compatible)
- `HistoryItem` gains `media_type: "image" | "video"` and `video_id: number | null`. For video rows
  `analysis_id` is the video-analysis id, `image_id` is null, and `thumbnail_url` is the most suspicious
  frame's thumbnail url (or null). `/api/history` gains query param `media` = `""` (both, default) |
  `image` | `video`; `q` and `verdict` filter both kinds. Merged list sorted by `created_at` desc.
- `DashboardStats` gains `total_videos` and `by_media: { image: n, video: n }` (counts of analyses).
  `total_analyses`, `avg_authenticity_score`, `by_verdict`, `trend` and `recent` now include video analyses.
  `total_images` stays images only.
- Frontend routes: image result `/analyses/:id`, video result `/video-analyses/:id`.

## Changelog
- v1 — initial contract.
- v2 — §6 video analysis (new endpoints, tables, ML functions; HistoryItem/DashboardStats additions).
- v2.1 — backend: `POST /api/videos` and `POST /api/video-analyses` return 503 if the installed ML pipeline lacks `probe_video`/`analyze_video` (additive; no shape changes).
