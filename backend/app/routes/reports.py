import logging
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db, utcnow
from app.deps import get_current_user_file, owned_analysis
from app.models import Analysis, Report, User
from app.services import storage
from app.services.report import generate_report_pdf

log = logging.getLogger("truthlens.reports")

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _is_stale(analysis: Analysis, report: Report) -> bool:
    """A cached report is stale if its file is gone or a restoration was added after it."""
    if storage.existing(report.pdf_path) is None:
        return True
    created = _aware(report.created_at)
    return any(_aware(r.created_at) > created for r in analysis.restorations)


@router.get("/{analysis_id}/pdf", response_class=FileResponse)
async def get_report_pdf(
    analysis_id: int, user: User = Depends(get_current_user_file), db: Session = Depends(get_db)
):
    analysis = owned_analysis(db, user, analysis_id)
    report = analysis.report
    if report is None or _is_stale(analysis, report):
        out = storage.root() / "reports" / f"report-{analysis.id}.pdf"
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            await run_in_threadpool(generate_report_pdf, analysis, user, str(out))
        except Exception as exc:
            log.exception("report generation failed for analysis %s", analysis.id)
            raise HTTPException(status_code=500, detail=f"Report generation failed: {exc}")
        if report is None:
            report = Report(analysis_id=analysis.id, pdf_path=storage.to_rel(out))
            db.add(report)
        else:
            report.pdf_path = storage.to_rel(out)
            report.created_at = utcnow()
        db.commit()
    path = storage.existing(report.pdf_path)
    if path is None:
        raise HTTPException(status_code=404, detail="Report file missing")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"truthlens-report-{analysis.id}.pdf",
        content_disposition_type="inline",
        headers={"Cache-Control": "private, no-cache"},
    )
