"""TruthLens FastAPI application. Run from backend/: `uvicorn app.main:app --reload`."""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import models  # noqa: F401  (register tables on Base.metadata)
from app.config import get_settings
from app.database import Base, engine
from app.routes import analyses, auth, history, images, reports, video_analyses, videos
from app.schemas import HealthOut
from app.services import ml, storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("truthlens")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    storage.ensure_dirs()
    if settings.is_sqlite:
        # Dev convenience; Postgres deployments run `alembic upgrade head` instead.
        Base.metadata.create_all(bind=engine)
    ml.export_ml_env()
    try:
        ml.start_warmup_thread()
    except Exception:  # pragma: no cover
        log.exception("could not start ML warmup thread")
    log.info("TruthLens API started (storage=%s, deep=%s)", settings.storage_path, settings.ML_ENABLE_DEEP)
    yield


app = FastAPI(title="TruthLens API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("%s %s -> unhandled error", request.method, request.url.path)
        raise
    ms = (time.perf_counter() - start) * 1000
    log.info("%s %s -> %s (%.0f ms)", request.method, request.url.path, response.status_code, ms)
    return response


# ---- centralized error handling: always {"detail": "..."} ----
@app.exception_handler(StarletteHTTPException)
async def http_exc_handler(_request: Request, exc: StarletteHTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse({"detail": detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_exc_handler(_request: Request, exc: RequestValidationError):
    parts = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
        msg = err.get("msg", "invalid value")
        msg = msg.removeprefix("Value error, ")
        parts.append(f"{'.'.join(loc)}: {msg}" if loc else msg)
    return JSONResponse({"detail": "; ".join(parts) or "Invalid request"}, status_code=422)


@app.exception_handler(Exception)
async def unhandled_exc_handler(_request: Request, exc: Exception):
    log.exception("unhandled error: %s", exc)
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


@app.get("/api/health", response_model=HealthOut, tags=["health"])
def health() -> HealthOut:
    return HealthOut(status="ok", ml_deep_enabled=get_settings().ML_ENABLE_DEEP, models_loaded=ml.models_loaded())


app.include_router(auth.router)
app.include_router(images.router)
app.include_router(analyses.router)
app.include_router(reports.router)
app.include_router(history.router)
app.include_router(videos.router)
app.include_router(video_analyses.router)
