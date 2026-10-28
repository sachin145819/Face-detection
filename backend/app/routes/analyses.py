import base64
import binascii
import io
import json
import logging
import math
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from PIL import Image as PILImage
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_current_user_file, owned_analysis, owned_image, owned_restoration
from app.models import Analysis, Restoration, User
from app.schemas import AnalysisCreateIn, AnalysisOut, RestorationOut, RestoreIn
from app.services import ml, storage
from app.services.serializers import analysis_out, restoration_out

log = logging.getLogger("truthlens.analyses")

router = APIRouter(prefix="/api", tags=["analyses"])

VERDICTS = ("authentic", "manipulated", "deepfake", "ai_generated")
MAX_MASK_BYTES = 20 * 1024 * 1024


def _json_default(o: Any) -> Any:
    # Defensive: tolerate numpy scalars / arrays / paths if the pipeline leaks them.
    if hasattr(o, "item") and callable(o.item):
        try:
            return o.item()
        except Exception:
            pass
    if hasattr(o, "tolist"):
        return o.tolist()
    if isinstance(o, (set, tuple)):
        return list(o)
    return str(o)


def _sanitize(result: dict) -> dict:
    def fix_floats(v: Any) -> Any:
        if isinstance(v, float) and not math.isfinite(v):
            return None
        if isinstance(v, dict):
            return {str(k): fix_floats(x) for k, x in v.items()}
        if isinstance(v, list):
            return [fix_floats(x) for x in v]
        return v

    return fix_floats(json.loads(json.dumps(result, default=_json_default)))


def _num(v: Any, default: float, lo: float, hi: float) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(f):
        return default
    return max(lo, min(hi, f))


def _relocate(path: Any, tmp_dir: Path, final_dir: Path) -> str | None:
    """Map a path the pipeline wrote inside tmp_dir to its location after the dir rename."""
    if not path:
        return None
    p = Path(str(path)).resolve()
    try:
        rel = p.relative_to(tmp_dir.resolve())
        return storage.to_rel(final_dir / rel)
    except ValueError:
        return storage.to_rel(p) if p.is_file() else None


@router.post("/analyses", response_model=AnalysisOut, status_code=status.HTTP_201_CREATED)
async def create_analysis(
    body: AnalysisCreateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> AnalysisOut:
    img = owned_image(db, user, body.image_id)
    src = storage.upload_path(img.stored_filename)
    if not src.is_file():
        raise HTTPException(status_code=404, detail="Image file missing on server")

    # Run the pipeline into a temp dir; only create the DB row once it succeeded.
    tmp_dir = storage.root() / "analyses" / f"tmp-{uuid.uuid4().hex}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        raw = await run_in_threadpool(ml.analyze_image, str(src), str(tmp_dir))
        if not isinstance(raw, dict):
            raise TypeError(f"pipeline returned {type(raw).__name__}, expected dict")
        result = _sanitize(raw)
    except ValueError as exc:
        storage.safe_rmtree(tmp_dir)
        raise HTTPException(status_code=400, detail=f"Image could not be analysed: {exc}")
    except Exception as exc:
        storage.safe_rmtree(tmp_dir)
        log.exception("analyze_image failed for image %s", img.id)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {type(exc).__name__}: {exc}")

    verdict = str(result.get("verdict") or "").strip().lower()
    if verdict not in VERDICTS:
        verdict = "manipulated" if verdict else "authentic"
    score = _num(result.get("authenticity_score"), 50.0, 0.0, 100.0)
    conf = _num(result.get("confidence"), 0.0, 0.0, 1.0)
    processing_ms = int(_num(result.get("processing_ms"), 0, 0, 1e12))

    analysis = Analysis(
        image_id=img.id,
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
        final_dir = storage.analysis_dir(analysis.id)
        storage.safe_rmtree(final_dir)  # stale leftovers from a previous DB
        tmp_dir.rename(final_dir)
        analysis.heatmap_path = _relocate(result.get("heatmap_path"), tmp_dir, final_dir)
        analysis.ela_path = _relocate(result.get("ela_path"), tmp_dir, final_dir)
        result["heatmap_path"] = analysis.heatmap_path
        result["ela_path"] = analysis.ela_path
        analysis.result_json = result
        db.commit()
    except Exception as exc:
        db.rollback()
        storage.safe_rmtree(tmp_dir)
        storage.safe_rmtree(final_dir)
        log.exception("failed to persist analysis")
        raise HTTPException(status_code=500, detail=f"Could not save analysis: {exc}")
    db.refresh(analysis)
    return analysis_out(analysis)


@router.get("/analyses/{analysis_id}", response_model=AnalysisOut)
def get_analysis(
    analysis_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> AnalysisOut:
    return analysis_out(owned_analysis(db, user, analysis_id))


def _png_response(path_str: str | None, what: str) -> FileResponse:
    p = storage.existing(path_str)
    if p is None:
        raise HTTPException(status_code=404, detail=f"No {what} available for this analysis")
    return FileResponse(p, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/analyses/{analysis_id}/heatmap", response_class=FileResponse)
def get_heatmap(
    analysis_id: int, user: User = Depends(get_current_user_file), db: Session = Depends(get_db)
):
    return _png_response(owned_analysis(db, user, analysis_id).heatmap_path, "heatmap")


@router.get("/analyses/{analysis_id}/ela", response_class=FileResponse)
def get_ela(
    analysis_id: int, user: User = Depends(get_current_user_file), db: Session = Depends(get_db)
):
    return _png_response(owned_analysis(db, user, analysis_id).ela_path, "ELA image")


def _decode_mask(data_url: str, dest: Path, size: tuple[int, int]) -> None:
    s = data_url.strip()
    if s.startswith("data:"):
        header, _, s = s.partition(",")
        if ";base64" not in header:
            raise HTTPException(status_code=400, detail="mask_base64 must be a base64 data URL")
    try:
        raw = base64.b64decode(s, validate=False)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="mask_base64 is not valid base64")
    if not raw or len(raw) > MAX_MASK_BYTES:
        raise HTTPException(status_code=400, detail="mask_base64 is empty or too large")
    try:
        with PILImage.open(io.BytesIO(raw)) as m:
            m.load()
            if m.mode in ("RGBA", "LA") or (m.mode == "P" and "transparency" in m.info):
                # Painted strokes on a transparent canvas: use alpha as the mask.
                mask = m.convert("RGBA").getchannel("A")
            else:
                mask = m.convert("L")
    except Exception:
        raise HTTPException(status_code=400, detail="mask_base64 is not a valid image")
    if mask.size != size:
        mask = mask.resize(size, PILImage.NEAREST)
    mask = mask.point(lambda v: 255 if v > 127 else 0)
    mask.save(dest, "PNG")


@router.post(
    "/analyses/{analysis_id}/restore", response_model=RestorationOut, status_code=status.HTTP_201_CREATED
)
async def restore(
    analysis_id: int,
    body: RestoreIn | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RestorationOut:
    body = body or RestoreIn()
    analysis = owned_analysis(db, user, analysis_id)
    img = analysis.image
    src = storage.upload_path(img.stored_filename)
    if not src.is_file():
        raise HTTPException(status_code=404, detail="Image file missing on server")

    restored_dir = storage.root() / "restored"
    restored_dir.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    out_path = restored_dir / f"{token}.png"
    mask_path: Path | None = None
    if body.mask_base64:
        mask_path = restored_dir / f"mask-{token}.png"
        _decode_mask(body.mask_base64, mask_path, (img.width, img.height))

    try:
        res = await run_in_threadpool(
            ml.restore_image,
            str(src),
            str(out_path),
            boxes=body.boxes,
            mask_path=str(mask_path) if mask_path else None,
        )
        if not isinstance(res, dict):
            raise TypeError(f"pipeline returned {type(res).__name__}, expected dict")
        final = Path(str(res.get("restored_path") or out_path))
        if not final.is_file():
            raise FileNotFoundError("restored image was not written")
    except Exception as exc:
        storage.safe_unlink(out_path)
        log.exception("restore_image failed for analysis %s", analysis.id)
        raise HTTPException(status_code=500, detail=f"Restoration failed: {type(exc).__name__}: {exc}")
    finally:
        storage.safe_unlink(mask_path)

    r = Restoration(
        analysis_id=analysis.id,
        user_id=user.id,
        method=str(res.get("method") or "unknown"),
        note=str(res.get("note") or "AI-reconstructed region — not original evidence"),
        restored_path=storage.to_rel(final),
    )
    db.add(r)
    try:
        db.commit()
    except Exception:
        db.rollback()
        storage.safe_unlink(final)
        raise
    db.refresh(r)
    return restoration_out(r)


@router.get("/restorations/{restoration_id}/file", response_class=FileResponse)
def get_restoration_file(
    restoration_id: int, user: User = Depends(get_current_user_file), db: Session = Depends(get_db)
):
    r = owned_restoration(db, user, restoration_id)
    p = storage.existing(r.restored_path)
    if p is None:
        raise HTTPException(status_code=404, detail="Restored file missing")
    return FileResponse(p, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})
