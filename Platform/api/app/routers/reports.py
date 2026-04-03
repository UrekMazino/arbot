from __future__ import annotations

import importlib
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from redis import Redis
from rq import Queue
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..deps import get_db_session, require_permissions
from ..models import Report, ReportFile, Run, User

router = APIRouter(tags=["reports"])


def _enqueue_report_job(run_id: str, report_id: str) -> str | None:
    try:
        redis_conn = Redis.from_url(settings.redis_url)
        queue = Queue("reports", connection=redis_conn)
        job = queue.enqueue(
            "tasks.report_generation.generate_report",
            run_id,
            report_id,
            job_timeout=600,
        )
        return job.id
    except Exception:
        return None


@router.post("/runs/{run_id}/reports/generate")
def generate_report(
    run_id: str,
    user: User = Depends(require_permissions("view_reports")),
    db: Session = Depends(get_db_session),
):
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    report = Report(
        run_id=run_id,
        status="queued",
        requested_by=user.id,
        requested_at=datetime.now(timezone.utc),
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    job_id = _enqueue_report_job(run_id, report.id)
    if not job_id:
        report.status = "failed"
        report.error_text = "Failed to enqueue report job"
        report.finished_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Queue unavailable")

    return {"report_id": report.id, "job_id": job_id, "status": report.status}


@router.get("/runs/{run_id}/reports")
def list_run_reports(
    run_id: str,
    _: User = Depends(require_permissions("view_reports")),
    db: Session = Depends(get_db_session),
):
    stmt = select(Report).where(Report.run_id == run_id).order_by(Report.requested_at.desc())
    rows = db.execute(stmt).scalars().all()
    return [
        {
            "id": row.id,
            "run_id": row.run_id,
            "status": row.status,
            "requested_by": row.requested_by,
            "requested_at": row.requested_at.isoformat() if row.requested_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "error_text": row.error_text,
        }
        for row in rows
    ]


@router.get("/reports/{report_id}")
def get_report(
    report_id: str,
    _: User = Depends(require_permissions("view_reports")),
    db: Session = Depends(get_db_session),
):
    row = db.get(Report, report_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return {
        "id": row.id,
        "run_id": row.run_id,
        "status": row.status,
        "requested_by": row.requested_by,
        "requested_at": row.requested_at.isoformat() if row.requested_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "error_text": row.error_text,
    }


@router.get("/reports/{report_id}/files")
def list_report_files(
    report_id: str,
    _: User = Depends(require_permissions("view_reports")),
    db: Session = Depends(get_db_session),
):
    stmt = select(ReportFile).where(ReportFile.report_id == report_id).order_by(ReportFile.created_at.asc())
    rows = db.execute(stmt).scalars().all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "path": row.path,
            "mime_type": row.mime_type,
            "size_bytes": row.size_bytes,
            "checksum": row.checksum,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


@router.get("/reports/{report_id}/files/{file_id}/download")
def report_file_download(
    report_id: str,
    file_id: str,
    _: User = Depends(require_permissions("view_reports")),
    db: Session = Depends(get_db_session),
):
    row = db.get(ReportFile, file_id)
    if not row or row.report_id != report_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report file not found")
    try:
        resolved = Path(str(row.path or "")).resolve()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file path")
    allowed_root = Path("/workspace").resolve()
    if not str(resolved).startswith(str(allowed_root)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="File outside allowed root")
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found on disk")
    return FileResponse(
        path=str(resolved),
        filename=row.name,
        media_type=row.mime_type or "application/octet-stream",
    )
