"""Video analyses: run the pipeline, fetch results, serve frame files, PDF report (CONTRACT §6.4)."""
import logging
import mimetypes
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user, get_current_user_file, owned_video, owned_video_analysis
from app.models import User, VideoAnalysis
from app.routes.analyses import VERDICTS, _num, _relocate, _sanitize
from app.schemas import VideoAnalysisCreateIn, VideoAnalysisOut
from app.services import ml, storage
from app.services.serializers import video_analysis_out
from app.services.video_report import generate_video_report_pdf

log = logging.getLogger("truthlens.video_analyses")

router = APIRouter(prefix="/api/video-analyses", tags=["video-analyses"])

FRAME_PATH_KEYS = ("thumbnail_path", "heatmap_path")


@router.post("", response_model=VideoAnalysisOut, status_code=status.HTTP_201_CREATED)
async def create_video_analysis(
    body: VideoAnalysisCreateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> VideoAnalysisOut:
    video = owned_video(db, user, body.video_id)
    src = storage.video_path(video.stored_filename)
    if not src.is_file():
        raise HTTPException(status_code=404, detail="Video file missing on server")

    # Run the pipeline into a temp dir; only create the DB row once it succeeded.
    tmp_dir = storage.root() / "video_analyses" / f"tmp-{uuid.uuid4().hex}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        raw = await run_in_threadpool(
            ml.analyze_video, str(src), str(tmp_dir), max_frames=get_settings().VIDEO_MAX_FRAMES
        )
        if not isinstance(raw, dict):
            raise TypeError(f"pipeline returned {type(raw).__name__}, expected dict")
        result = _sanitize(raw)
    except ValueError as exc:
        storage.safe_rmtree(tmp_dir)
        raise HTTPException(status_code=400, detail=f"Video could not be analysed: {exc}")
    except ml.VideoUnsupportedError as exc:
        storage.safe_rmtree(tmp_dir)
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        storage.safe_rmtree(tmp_dir)
        log.exception("analyze_video failed for video %s", video.id)
        raise HTTPException(status_code=500, detail=f"Video analysis failed: {type(exc).__name__}: {exc}")

    verdict = str(result.get("verdict") or "").strip().lower()
    if verdict not in VERDICTS:
        verdict = "manipulated" if verdict else "authentic"
    score = _num(result.get("authenticity_score"), 50.0, 0.0, 100.0)
    conf = _num(result.get("confidence"), 0.0, 0.0, 1.0)
    processing_ms = int(_num(result.get("processing_ms"), 0, 0, 1e12))
    result["media_type"] = "video"

    analysis = VideoAnalysis(
        video_id=video.id,
        user_id=user.id,
        verdict=verdict,
        authenticity_score=score,
        confidence=conf,
        result_json={},
        processing_ms=processing_ms,
    )
    final_dir: Path | None = None
    try:
        db.add(analysis)
        db.flush()  # assigns id
        final_dir = storage.video_analysis_dir(analysis.id)
        storage.safe_rmtree(final_dir)  # stale leftovers from a previous DB
        tmp_dir.rename(final_dir)
        frames = result.get("frames")
        if not isinstance(frames, list):
            result["frames"] = frames = []
        for f in frames:
            if isinstance(f, dict):
                for k in FRAME_PATH_KEYS:
                    f[k] = _relocate(f.get(k), tmp_dir, final_dir)
        analysis.result_json = result
        db.commit()
    except Exception as exc:
        db.rollback()
        storage.safe_rmtree(tmp_dir)
        storage.safe_rmtree(final_dir)
        log.exception("failed to persist video analysis")
        raise HTTPException(status_code=500, detail=f"Could not save video analysis: {exc}")
    db.refresh(analysis)
    return video_analysis_out(analysis)


@router.get("/{analysis_id}", response_model=VideoAnalysisOut)
def get_video_analysis(
    analysis_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> VideoAnalysisOut:
    return video_analysis_out(owned_video_analysis(db, user, analysis_id))


def _safe_child(directory: Path, name: str) -> Path | None:
    """Resolve `name` as a plain basename directly inside `directory`; None for anything else."""
    if not name or name in (".", "..") or name.startswith(".") or name != Path(name).name:
        return None
    if "/" in name or "\\" in name or "\x00" in name:
        return None
    base = directory.resolve()
    p = (base / name).resolve()
    if p.parent != base or not p.is_file():
        return None
    return p


@router.get("/{analysis_id}/files/{name}", response_class=FileResponse)
def get_video_analysis_file(
    analysis_id: int, name: str, user: User = Depends(get_current_user_file), db: Session = Depends(get_db)
):
    a = owned_video_analysis(db, user, analysis_id)
    p = _safe_child(storage.video_analysis_dir(a.id), name)
    if p is None:
        raise HTTPException(status_code=404, detail="File not found")
    media_type = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    return FileResponse(p, media_type=media_type, headers={"Cache-Control": "private, max-age=3600"})


def _report_file(a: VideoAnalysis) -> Path:
    return storage.root() / "reports" / f"video-report-{a.id}.pdf"


@router.get("/{analysis_id}/report", response_class=FileResponse)
async def get_video_report(
    analysis_id: int, user: User = Depends(get_current_user_file), db: Session = Depends(get_db)
) -> Any:
    a = owned_video_analysis(db, user, analysis_id)
    if storage.existing(a.report_path) is None:
        out = _report_file(a)
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            await run_in_threadpool(generate_video_report_pdf, a, user, str(out))
        except Exception as exc:
            log.exception("video report generation failed for video analysis %s", a.id)
            raise HTTPException(status_code=500, detail=f"Report generation failed: {exc}")
        a.report_path = storage.to_rel(out)
        db.commit()
    path = storage.existing(a.report_path)
    if path is None:
        raise HTTPException(status_code=404, detail="Report file missing")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"truthlens-video-report-{a.id}.pdf",
        content_disposition_type="inline",
        headers={"Cache-Control": "private, no-cache"},
    )
