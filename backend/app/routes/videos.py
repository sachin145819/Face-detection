"""Video upload / listing / streaming (docs/CONTRACT.md §6.4)."""
import hashlib
import logging
import math
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user, get_current_user_file, owned_video
from app.models import User, Video
from app.schemas import VideoOut
from app.services import ml, storage
from app.services.serializers import video_out

log = logging.getLogger("truthlens.videos")

router = APIRouter(prefix="/api/videos", tags=["videos"])

# extension -> canonical mime type
ALLOWED_EXTS = {
    "mp4": "video/mp4",
    "mov": "video/quicktime",
    "webm": "video/webm",
    "avi": "video/x-msvideo",
    "mkv": "video/x-matroska",
}
# Browsers / OSes report all sorts of things for these containers; accept any video/* plus the
# generic types some clients send for unknown files. The real check is probe_video().
GENERIC_MIMES = {"", "application/octet-stream", "binary/octet-stream", "application/x-matroska"}
CHUNK = 1024 * 1024


def _clean_filename(name: str | None, ext: str) -> str:
    base = Path(name or "").name.strip()
    base = "".join(ch for ch in base if ch.isprintable())[:255]
    return base or f"upload.{ext}"


def _ext_of(name: str | None) -> str:
    return Path(name or "").suffix.lower().lstrip(".")


def _num(v: Any, default: float = 0.0) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) and f >= 0 else default


def _copy_upload(file: UploadFile, dest: Path, limit: int) -> tuple[int, str]:
    """Stream the (already spooled) upload to `dest` in chunks. Returns (size, sha256).

    Raises OverflowError as soon as more than `limit` bytes have been seen.
    """
    h = hashlib.sha256()
    size = 0
    src = file.file
    src.seek(0)
    with open(dest, "wb") as out:
        while True:
            chunk = src.read(CHUNK)
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise OverflowError
            h.update(chunk)
            out.write(chunk)
    return size, h.hexdigest()


@router.post("", response_model=VideoOut, status_code=status.HTTP_201_CREATED)
async def upload_video(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VideoOut:
    settings = get_settings()
    limit = settings.max_video_bytes
    too_large = HTTPException(
        status_code=413, detail=f"File too large. Maximum video size is {settings.MAX_VIDEO_MB} MB."
    )
    ext = _ext_of(file.filename)
    if ext not in ALLOWED_EXTS:
        raise HTTPException(
            status_code=400, detail="Unsupported video type. Upload an MP4, MOV, WebM, AVI or MKV file."
        )
    ctype = (file.content_type or "").split(";")[0].strip().lower()
    if not (ctype.startswith("video/") or ctype in GENERIC_MIMES):
        raise HTTPException(status_code=400, detail=f"Unsupported content type '{ctype}' for a video upload.")
    if file.size is not None and file.size > limit:
        raise too_large

    stored = f"{uuid.uuid4().hex}.{ext}"
    dest = storage.video_path(stored)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        size, sha = await run_in_threadpool(_copy_upload, file, dest, limit)
    except OverflowError:
        storage.safe_unlink(dest)
        raise too_large
    except Exception:
        storage.safe_unlink(dest)
        raise
    if size == 0:
        storage.safe_unlink(dest)
        raise HTTPException(status_code=400, detail="Empty file.")

    try:
        info = await run_in_threadpool(ml.probe_video, str(dest))
        if not isinstance(info, dict):
            raise TypeError(f"probe_video returned {type(info).__name__}, expected dict")
    except ValueError as exc:
        storage.safe_unlink(dest)
        raise HTTPException(status_code=400, detail=f"File is not a decodable video: {exc}")
    except ml.VideoUnsupportedError as exc:
        storage.safe_unlink(dest)
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        storage.safe_unlink(dest)
        log.exception("probe_video failed")
        raise HTTPException(status_code=500, detail=f"Could not inspect video: {type(exc).__name__}: {exc}")

    width, height = int(_num(info.get("width"))), int(_num(info.get("height")))
    if width <= 0 or height <= 0:
        storage.safe_unlink(dest)
        raise HTTPException(status_code=400, detail="Video has no decodable frames.")

    video = Video(
        user_id=user.id,
        original_filename=_clean_filename(file.filename, ext),
        stored_filename=stored,
        mime_type=ALLOWED_EXTS[ext],
        size_bytes=size,
        width=width,
        height=height,
        duration_s=round(_num(info.get("duration_s")), 3),
        fps=round(_num(info.get("fps")), 3),
        frame_count=int(_num(info.get("frame_count"))),
        sha256=sha,
    )
    db.add(video)
    try:
        db.commit()
    except Exception:
        db.rollback()
        storage.safe_unlink(dest)
        raise
    db.refresh(video)
    return video_out(video)


@router.get("", response_model=list[VideoOut])
def list_videos(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[VideoOut]:
    rows = db.scalars(
        select(Video).where(Video.user_id == user.id).order_by(Video.uploaded_at.desc(), Video.id.desc())
    ).all()
    return [video_out(v) for v in rows]


@router.get("/{video_id}", response_model=VideoOut)
def get_video(
    video_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> VideoOut:
    return video_out(owned_video(db, user, video_id))


@router.get("/{video_id}/file", response_class=FileResponse)
def get_video_file(
    video_id: int, user: User = Depends(get_current_user_file), db: Session = Depends(get_db)
):
    # Starlette's FileResponse honours Range / If-Range (206 Partial Content) so <video> can seek.
    v = owned_video(db, user, video_id)
    path = storage.video_path(v.stored_filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Video file missing")
    return FileResponse(path, media_type=v.mime_type, headers={"Cache-Control": "private, max-age=3600"})


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(
    video_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Response:
    v = owned_video(db, user, video_id)
    files: list = [storage.video_path(v.stored_filename)]
    dirs = []
    for a in v.analyses:
        dirs.append(storage.video_analysis_dir(a.id))
        files.append(storage.to_abs(a.report_path))
    db.delete(v)
    db.commit()
    for f in files:
        storage.safe_unlink(f)
    for d in dirs:
        storage.safe_rmtree(d)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
