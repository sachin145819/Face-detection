"""Shared FastAPI dependencies: auth + per-user resource lookup."""
from typing import Optional

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Analysis, Image, Restoration, User, Video, VideoAnalysis
from app.services.security import decode_access_token

_bearer = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def _user_from_token(token: Optional[str], db: Session) -> User:
    if not token:
        raise _UNAUTHORIZED
    user_id = decode_access_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.get(User, user_id)
    if user is None:
        raise _UNAUTHORIZED
    return user


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    return _user_from_token(creds.credentials if creds else None, db)


def get_current_user_file(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    token: Optional[str] = Query(default=None, description="JWT, for <img src> / <a href> use"),
    db: Session = Depends(get_db),
) -> User:
    """Like get_current_user but also accepts `?token=` (for 📎 binary endpoints)."""
    return _user_from_token(creds.credentials if creds else token, db)


def owned_image(db: Session, user: User, image_id: int) -> Image:
    img = db.scalar(select(Image).where(Image.id == image_id, Image.user_id == user.id))
    if img is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return img


def owned_analysis(db: Session, user: User, analysis_id: int) -> Analysis:
    a = db.scalar(select(Analysis).where(Analysis.id == analysis_id, Analysis.user_id == user.id))
    if a is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return a


def owned_restoration(db: Session, user: User, restoration_id: int) -> Restoration:
    r = db.scalar(
        select(Restoration).where(Restoration.id == restoration_id, Restoration.user_id == user.id)
    )
    if r is None:
        raise HTTPException(status_code=404, detail="Restoration not found")
    return r


def owned_video(db: Session, user: User, video_id: int) -> Video:
    v = db.scalar(select(Video).where(Video.id == video_id, Video.user_id == user.id))
    if v is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return v


def owned_video_analysis(db: Session, user: User, analysis_id: int) -> VideoAnalysis:
    a = db.scalar(
        select(VideoAnalysis).where(VideoAnalysis.id == analysis_id, VideoAnalysis.user_id == user.id)
    )
    if a is None:
        raise HTTPException(status_code=404, detail="Video analysis not found")
    return a
