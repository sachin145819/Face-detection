"""Pydantic request/response schemas (docs/CONTRACT.md §5, §6)."""
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_serializer, field_validator


def _as_utc(dt: datetime) -> datetime:
    # SQLite drops tzinfo; everything we store is UTC.
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class _Out(BaseModel):
    @field_serializer("*", when_used="json-unless-none", check_fields=False)
    def _ser_dt(self, v: Any) -> Any:
        if isinstance(v, datetime):
            return _as_utc(v).isoformat().replace("+00:00", "Z")
        return v


# ---------- auth ----------
class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(_Out):
    id: int
    name: str
    email: str
    created_at: datetime


class TokenOut(_Out):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserOut


# ---------- images ----------
class ImageOut(_Out):
    id: int
    original_filename: str
    mime_type: str
    size_bytes: int
    width: int
    height: int
    uploaded_at: datetime
    url: str


# ---------- analyses ----------
class AnalysisCreateIn(BaseModel):
    image_id: int


class RestorationOut(_Out):
    id: int
    analysis_id: int
    method: str
    note: str
    created_at: datetime
    url: str


class AnalysisOut(_Out):
    id: int
    image_id: int
    verdict: str
    authenticity_score: float
    confidence: float
    created_at: datetime
    processing_ms: int
    result: dict[str, Any]
    image: ImageOut
    heatmap_url: Optional[str]
    ela_url: Optional[str]
    report_url: str
    restorations: list[RestorationOut]


class RestoreIn(BaseModel):
    boxes: Optional[list[list[int]]] = None
    mask_base64: Optional[str] = None

    @field_validator("boxes")
    @classmethod
    def _check_boxes(cls, v: Optional[list[list[int]]]) -> Optional[list[list[int]]]:
        if v is None:
            return v
        if len(v) > 100:
            raise ValueError("too many boxes (max 100)")
        for b in v:
            if len(b) != 4:
                raise ValueError("each box must be [x, y, w, h]")
            if b[2] <= 0 or b[3] <= 0:
                raise ValueError("box width/height must be positive")
        return v or None


# ---------- videos ----------
class VideoOut(_Out):
    id: int
    original_filename: str
    mime_type: str
    size_bytes: int
    width: int
    height: int
    duration_s: float
    fps: float
    frame_count: int
    uploaded_at: datetime
    url: str


class VideoAnalysisCreateIn(BaseModel):
    video_id: int


class VideoAnalysisOut(_Out):
    id: int
    video_id: int
    verdict: str
    authenticity_score: float
    confidence: float
    created_at: datetime
    processing_ms: int
    result: dict[str, Any]
    video: VideoOut
    report_url: str


# ---------- history / dashboard ----------
class HistoryItem(_Out):
    analysis_id: int
    image_id: Optional[int]
    original_filename: str
    verdict: str
    authenticity_score: float
    confidence: float
    created_at: datetime
    thumbnail_url: Optional[str]
    media_type: Literal["image", "video"] = "image"
    video_id: Optional[int] = None


class HistoryPage(BaseModel):
    items: list[HistoryItem]
    total: int
    page: int
    page_size: int


class VerdictCounts(BaseModel):
    authentic: int = 0
    manipulated: int = 0
    deepfake: int = 0
    ai_generated: int = 0


class TrendPoint(VerdictCounts):
    date: str


class MediaCounts(BaseModel):
    image: int = 0
    video: int = 0


class DashboardStats(BaseModel):
    total_images: int
    total_videos: int
    total_analyses: int
    avg_authenticity_score: float
    by_verdict: VerdictCounts
    by_media: MediaCounts
    trend: list[TrendPoint]
    recent: list[HistoryItem]


class HealthOut(BaseModel):
    status: str
    ml_deep_enabled: bool
    models_loaded: bool
