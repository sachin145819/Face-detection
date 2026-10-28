"""Filesystem layout under STORAGE_DIR. Paths are stored in the DB relative to STORAGE_DIR."""
import shutil
from pathlib import Path
from typing import Optional

from app.config import get_settings

SUBDIRS = ("uploads", "analyses", "restored", "reports", "videos", "video_analyses")


def root() -> Path:
    return get_settings().storage_path


def ensure_dirs() -> None:
    r = root()
    for sub in SUBDIRS:
        (r / sub).mkdir(parents=True, exist_ok=True)


def to_rel(path: Optional[str | Path]) -> Optional[str]:
    """Store a path relative to STORAGE_DIR when it lives inside it, else absolute."""
    if not path:
        return None
    p = Path(path).resolve()
    try:
        return p.relative_to(root()).as_posix()
    except ValueError:
        return str(p)


def to_abs(path: Optional[str]) -> Optional[Path]:
    if not path:
        return None
    p = Path(path)
    return p if p.is_absolute() else root() / p


def existing(path: Optional[str]) -> Optional[Path]:
    p = to_abs(path)
    return p if p is not None and p.is_file() else None


def upload_path(stored_filename: str) -> Path:
    return root() / "uploads" / stored_filename


def analysis_dir(analysis_id: int) -> Path:
    return root() / "analyses" / str(analysis_id)


def video_path(stored_filename: str) -> Path:
    return root() / "videos" / stored_filename


def video_analysis_dir(analysis_id: int) -> Path:
    return root() / "video_analyses" / str(analysis_id)


def safe_unlink(path: Optional[str | Path]) -> None:
    if not path:
        return
    p = to_abs(str(path)) if not isinstance(path, Path) else path
    try:
        if p is not None and p.is_file():
            p.unlink()
    except OSError:
        pass


def safe_rmtree(path: Optional[Path]) -> None:
    if path is not None and path.exists():
        shutil.rmtree(path, ignore_errors=True)
