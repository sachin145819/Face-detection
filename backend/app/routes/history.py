from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Analysis, Image, User, Video, VideoAnalysis
from app.schemas import DashboardStats, HistoryItem, HistoryPage, MediaCounts, TrendPoint, VerdictCounts
from app.services.serializers import history_item, video_history_item

router = APIRouter(prefix="/api", tags=["history"])

VERDICTS = ("authentic", "manipulated", "deepfake", "ai_generated")


def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


MEDIA = ("image", "video")


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _sort_key(item: HistoryItem):
    return (_aware(item.created_at), item.analysis_id, item.media_type == "video")


def _image_rows(db: Session, conds: list, limit: int) -> list[HistoryItem]:
    rows = db.execute(
        select(Analysis, Image)
        .join(Image, Analysis.image_id == Image.id)
        .where(*conds)
        .order_by(Analysis.created_at.desc(), Analysis.id.desc())
        .limit(limit)
    ).all()
    return [history_item(a, i) for a, i in rows]


def _video_rows(db: Session, conds: list, limit: int) -> list[HistoryItem]:
    rows = db.execute(
        select(VideoAnalysis, Video)
        .join(Video, VideoAnalysis.video_id == Video.id)
        .where(*conds)
        .order_by(VideoAnalysis.created_at.desc(), VideoAnalysis.id.desc())
        .limit(limit)
    ).all()
    return [video_history_item(a, v) for a, v in rows]


def _merged(image_items: list[HistoryItem], video_items: list[HistoryItem]) -> list[HistoryItem]:
    return sorted(image_items + video_items, key=_sort_key, reverse=True)


@router.get("/history", response_model=HistoryPage)
def history(
    q: Optional[str] = Query(default=None, max_length=255),
    verdict: Optional[str] = Query(default=None),
    media: Optional[str] = Query(default=None, description='"" (both), "image" or "video"'),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HistoryPage:
    m = (media or "").strip().lower()
    if m in ("", "all"):
        kinds = MEDIA
    elif m in MEDIA:
        kinds = (m,)
    else:
        raise HTTPException(status_code=400, detail="media must be one of: image, video")

    img_conds = [Analysis.user_id == user.id]
    vid_conds = [VideoAnalysis.user_id == user.id]
    if q and q.strip():
        pattern = f"%{_escape_like(q.strip())}%"
        img_conds.append(Image.original_filename.ilike(pattern, escape="\\"))
        vid_conds.append(Video.original_filename.ilike(pattern, escape="\\"))
    if verdict and verdict.strip() and verdict.strip().lower() != "all":
        v = verdict.strip().lower()
        if v not in VERDICTS:
            raise HTTPException(status_code=400, detail=f"verdict must be one of: {', '.join(VERDICTS)}")
        img_conds.append(Analysis.verdict == v)
        vid_conds.append(VideoAnalysis.verdict == v)

    # The merged page can only contain rows from the top (offset + page_size) of each kind,
    # so fetch that many of each, merge in Python and slice.
    need = page * page_size
    total = 0
    image_items: list[HistoryItem] = []
    video_items: list[HistoryItem] = []
    if "image" in kinds:
        total += db.scalar(
            select(func.count()).select_from(Analysis).join(Image, Analysis.image_id == Image.id).where(*img_conds)
        ) or 0
        image_items = _image_rows(db, img_conds, need)
    if "video" in kinds:
        total += db.scalar(
            select(func.count())
            .select_from(VideoAnalysis)
            .join(Video, VideoAnalysis.video_id == Video.id)
            .where(*vid_conds)
        ) or 0
        video_items = _video_rows(db, vid_conds, need)
    items = _merged(image_items, video_items)[(page - 1) * page_size: need]
    return HistoryPage(items=items, total=total, page=page, page_size=page_size)


def _utc_date(dt: datetime):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date()


@router.get("/dashboard/stats", response_model=DashboardStats)
def dashboard_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> DashboardStats:
    total_images = db.scalar(select(func.count(Image.id)).where(Image.user_id == user.id)) or 0
    total_videos = db.scalar(select(func.count(Video.id)).where(Video.user_id == user.id)) or 0
    n_img, sum_img = db.execute(
        select(func.count(Analysis.id), func.sum(Analysis.authenticity_score)).where(Analysis.user_id == user.id)
    ).one()
    n_vid, sum_vid = db.execute(
        select(func.count(VideoAnalysis.id), func.sum(VideoAnalysis.authenticity_score)).where(
            VideoAnalysis.user_id == user.id
        )
    ).one()
    n_img, n_vid = int(n_img or 0), int(n_vid or 0)
    total_analyses = n_img + n_vid
    score_sum = float(sum_img or 0.0) + float(sum_vid or 0.0)
    avg = round(score_sum / total_analyses, 2) if total_analyses else 0.0

    by_verdict = VerdictCounts()
    for model in (Analysis, VideoAnalysis):
        for v, n in db.execute(
            select(model.verdict, func.count(model.id)).where(model.user_id == user.id).group_by(model.verdict)
        ).all():
            if v in VERDICTS:
                setattr(by_verdict, v, getattr(by_verdict, v) + int(n))

    # 7-day trend (today incl.), bucketed in Python so it works the same on SQLite and Postgres.
    today = datetime.now(timezone.utc).date()
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    buckets = {d: TrendPoint(date=d.isoformat()) for d in days}
    since = datetime.combine(days[0], datetime.min.time(), tzinfo=timezone.utc) - timedelta(days=1)
    for model in (Analysis, VideoAnalysis):
        for v, created in db.execute(
            select(model.verdict, model.created_at).where(model.user_id == user.id, model.created_at >= since)
        ).all():
            d = _utc_date(created)
            if d in buckets and v in VERDICTS:
                setattr(buckets[d], v, getattr(buckets[d], v) + 1)

    recent = _merged(
        _image_rows(db, [Analysis.user_id == user.id], 5),
        _video_rows(db, [VideoAnalysis.user_id == user.id], 5),
    )[:5]

    return DashboardStats(
        total_images=total_images,
        total_videos=total_videos,
        total_analyses=total_analyses,
        avg_authenticity_score=avg,
        by_verdict=by_verdict,
        by_media=MediaCounts(image=n_img, video=n_vid),
        trend=[buckets[d] for d in days],
        recent=recent,
    )
