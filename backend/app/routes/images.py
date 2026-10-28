import hashlib
import io
import uuid
import warnings
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from PIL import Image as PILImage
from PIL import UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user, get_current_user_file, owned_image
from app.models import Image, User
from app.schemas import ImageOut
from app.services import storage
from app.services.serializers import image_out

router = APIRouter(prefix="/api/images", tags=["images"])

# Pillow format -> (mime type, extension)
ALLOWED_FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}
MAX_PIXELS = 100_000_000  # guard against decompression bombs


def _sniff_image(data: bytes) -> tuple[str, int, int]:
    """Validate real image content with Pillow. Returns (format, width, height)."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", PILImage.DecompressionBombWarning)
            with PILImage.open(io.BytesIO(data)) as im:
                fmt = (im.format or "").upper()
                if fmt not in ALLOWED_FORMATS:
                    raise HTTPException(
                        status_code=400,
                        detail="Unsupported image type. Upload a JPEG, PNG or WebP image.",
                    )
                width, height = im.size
                im.verify()
            # verify() leaves the image unusable; reopen and fully decode to catch truncation.
            with PILImage.open(io.BytesIO(data)) as im2:
                im2.load()
                # Store the as-displayed size: the ML pipeline returns box coordinates
                # in EXIF-rotated orientation, and browsers render the rotated image.
                if im2.getexif().get(0x0112) in (5, 6, 7, 8):
                    width, height = height, width
    except HTTPException:
        raise
    except (UnidentifiedImageError, PILImage.DecompressionBombError, PILImage.DecompressionBombWarning):
        raise HTTPException(
            status_code=400, detail="File is not a valid JPEG, PNG or WebP image."
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Image file is corrupted or truncated.")
    if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
        raise HTTPException(status_code=400, detail="Image dimensions are not supported.")
    return fmt, width, height


def _clean_filename(name: str | None, ext: str) -> str:
    base = Path(name or "").name.strip()
    base = "".join(ch for ch in base if ch.isprintable())[:255]
    return base or f"upload.{ext}"


@router.post("", response_model=ImageOut, status_code=status.HTTP_201_CREATED)
async def upload_image(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImageOut:
    settings = get_settings()
    limit = settings.max_upload_bytes
    too_large = HTTPException(
        status_code=413, detail=f"File too large. Maximum size is {settings.MAX_UPLOAD_MB} MB."
    )
    if file.size is not None and file.size > limit:
        raise too_large
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise too_large
    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")

    fmt, width, height = await run_in_threadpool(_sniff_image, data)
    mime, ext = ALLOWED_FORMATS[fmt]
    stored = f"{uuid.uuid4().hex}.{ext}"
    dest = storage.upload_path(stored)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)

    img = Image(
        user_id=user.id,
        original_filename=_clean_filename(file.filename, ext),
        stored_filename=stored,
        mime_type=mime,
        size_bytes=len(data),
        width=width,
        height=height,
        sha256=hashlib.sha256(data).hexdigest(),
    )
    db.add(img)
    try:
        db.commit()
    except Exception:
        db.rollback()
        storage.safe_unlink(dest)
        raise
    db.refresh(img)
    return image_out(img)


@router.get("", response_model=list[ImageOut])
def list_images(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[ImageOut]:
    rows = db.scalars(
        select(Image).where(Image.user_id == user.id).order_by(Image.uploaded_at.desc(), Image.id.desc())
    ).all()
    return [image_out(i) for i in rows]


@router.get("/{image_id}", response_model=ImageOut)
def get_image(
    image_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ImageOut:
    return image_out(owned_image(db, user, image_id))


@router.get("/{image_id}/file", response_class=FileResponse)
def get_image_file(
    image_id: int, user: User = Depends(get_current_user_file), db: Session = Depends(get_db)
):
    img = owned_image(db, user, image_id)
    path = storage.upload_path(img.stored_filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Image file missing")
    return FileResponse(path, media_type=img.mime_type, headers={"Cache-Control": "private, max-age=3600"})


@router.delete("/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_image(
    image_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Response:
    img = owned_image(db, user, image_id)
    files: list = [storage.upload_path(img.stored_filename)]
    dirs = []
    for a in img.analyses:
        dirs.append(storage.analysis_dir(a.id))
        files += [storage.to_abs(a.heatmap_path), storage.to_abs(a.ela_path)]
        files += [storage.to_abs(r.restored_path) for r in a.restorations]
        if a.report is not None:
            files.append(storage.to_abs(a.report.pdf_path))
    db.delete(img)
    db.commit()
    for f in files:
        storage.safe_unlink(f)
    for d in dirs:
        storage.safe_rmtree(d)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
