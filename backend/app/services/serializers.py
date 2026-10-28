"""ORM -> response schema conversion. All file URLs are relative /api/... paths."""
import copy
from pathlib import Path
from typing import Any, Optional

from app.models import Analysis, Image, Restoration, User, Video, VideoAnalysis
from app.schemas import (
    AnalysisOut,
    HistoryItem,
    ImageOut,
    RestorationOut,
    UserOut,
    VideoAnalysisOut,
    VideoOut,
)
from app.services import storage

_STRIP_KEYS = ("heatmap_path", "ela_path")


def user_out(u: User) -> UserOut:
    return UserOut(id=u.id, name=u.name, email=u.email, created_at=u.created_at)


def image_out(img: Image) -> ImageOut:
    return ImageOut(
        id=img.id,
        original_filename=img.original_filename,
        mime_type=img.mime_type,
        size_bytes=img.size_bytes,
        width=img.width,
        height=img.height,
        uploaded_at=img.uploaded_at,
        url=f"/api/images/{img.id}/file",
    )


def restoration_out(r: Restoration) -> RestorationOut:
    return RestorationOut(
        id=r.id,
        analysis_id=r.analysis_id,
        method=r.method,
        note=r.note,
        created_at=r.created_at,
        url=f"/api/restorations/{r.id}/file",
    )


def public_result(result: dict[str, Any] | None) -> dict[str, Any]:
    return {k: v for k, v in (result or {}).items() if k not in _STRIP_KEYS}


def analysis_out(a: Analysis) -> AnalysisOut:
    return AnalysisOut(
        id=a.id,
        image_id=a.image_id,
        verdict=a.verdict,
        authenticity_score=a.authenticity_score,
        confidence=a.confidence,
        created_at=a.created_at,
        processing_ms=a.processing_ms,
        result=public_result(a.result_json),
        image=image_out(a.image),
        heatmap_url=f"/api/analyses/{a.id}/heatmap" if storage.existing(a.heatmap_path) else None,
        ela_url=f"/api/analyses/{a.id}/ela" if storage.existing(a.ela_path) else None,
        report_url=f"/api/reports/{a.id}/pdf",
        restorations=[restoration_out(r) for r in a.restorations],
    )


def history_item(a: Analysis, img: Image) -> HistoryItem:
    return HistoryItem(
        analysis_id=a.id,
        image_id=img.id,
        original_filename=img.original_filename,
        verdict=a.verdict,
        authenticity_score=a.authenticity_score,
        confidence=a.confidence,
        created_at=a.created_at,
        thumbnail_url=f"/api/images/{img.id}/file",
        media_type="image",
        video_id=None,
    )


# ---------------------------------------------------------------- videos
def video_out(v: Video) -> VideoOut:
    return VideoOut(
        id=v.id,
        original_filename=v.original_filename,
        mime_type=v.mime_type,
        size_bytes=v.size_bytes,
        width=v.width,
        height=v.height,
        duration_s=v.duration_s,
        fps=v.fps,
        frame_count=v.frame_count,
        uploaded_at=v.uploaded_at,
        url=f"/api/videos/{v.id}/file",
    )


def video_file_url(analysis_id: int, path: Any) -> Optional[str]:
    """URL for a file the pipeline wrote into video_analyses/<id>/, or None if it isn't there."""
    if not path or not isinstance(path, str):
        return None
    name = Path(path).name
    if not name or name.startswith("."):
        return None
    if not (storage.video_analysis_dir(analysis_id) / name).is_file():
        return None
    return f"/api/video-analyses/{analysis_id}/files/{name}"


def public_video_result(a: VideoAnalysis) -> dict[str, Any]:
    """analyze_video result with every frames[].*_path replaced by a *_url."""
    result = copy.deepcopy(a.result_json or {})
    frames = result.get("frames")
    if isinstance(frames, list):
        for f in frames:
            if not isinstance(f, dict):
                continue
            f["thumbnail_url"] = video_file_url(a.id, f.pop("thumbnail_path", None))
            f["heatmap_url"] = video_file_url(a.id, f.pop("heatmap_path", None))
    # never leak server paths anywhere at the top level either
    for k in [k for k in result if k.endswith("_path")]:
        result.pop(k, None)
    return result


def top_frame(result: dict[str, Any] | None) -> Optional[dict[str, Any]]:
    """The most suspicious sampled frame (top_frames[0], else the max-suspicion frame)."""
    frames = [f for f in ((result or {}).get("frames") or []) if isinstance(f, dict)]
    if not frames:
        return None
    top = (result or {}).get("top_frames") or []
    if top and isinstance(top[0], int) and not isinstance(top[0], bool) and 0 <= top[0] < len(frames):
        return frames[top[0]]

    def susp(f: dict) -> float:
        try:
            return float(f.get("suspicion") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    return max(frames, key=susp)


def video_analysis_out(a: VideoAnalysis) -> VideoAnalysisOut:
    return VideoAnalysisOut(
        id=a.id,
        video_id=a.video_id,
        verdict=a.verdict,
        authenticity_score=a.authenticity_score,
        confidence=a.confidence,
        created_at=a.created_at,
        processing_ms=a.processing_ms,
        result=public_video_result(a),
        video=video_out(a.video),
        report_url=f"/api/video-analyses/{a.id}/report",
    )


def video_history_item(a: VideoAnalysis, v: Video) -> HistoryItem:
    tf = top_frame(a.result_json)
    return HistoryItem(
        analysis_id=a.id,
        image_id=None,
        original_filename=v.original_filename,
        verdict=a.verdict,
        authenticity_score=a.authenticity_score,
        confidence=a.confidence,
        created_at=a.created_at,
        thumbnail_url=video_file_url(a.id, tf.get("thumbnail_path")) if tf else None,
        media_type="video",
        video_id=v.id,
    )
