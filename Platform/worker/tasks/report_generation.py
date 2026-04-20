from __future__ import annotations

import mimetypes
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.database import SessionLocal  # noqa: E402
from app.models import Report, ReportFile, Run  # noqa: E402
from app.services.live_report import materialize_live_run_report  # noqa: E402


def _mime_type_for(path: Path) -> str | None:
    mime_type, _ = mimetypes.guess_type(str(path))
    return mime_type


def generate_report(run_id: str, report_id: str) -> dict:
    """Worker entrypoint for DB-backed report generation."""
    db: Session = SessionLocal()
    try:
        report = db.get(Report, report_id)
        run = db.get(Run, run_id)
        if not report or not run:
            return {"ok": False, "error": "run/report not found"}

        report.status = "running"
        db.commit()

        result = materialize_live_run_report(db, run)
        if not result.get("saved"):
            raise RuntimeError(str(result.get("detail") or "live_report_failed"))

        db.execute(delete(ReportFile).where(ReportFile.report_id == report.id))

        artifact_files = result.get("artifacts") if isinstance(result.get("artifacts"), list) else []
        linked_files = 0
        for artifact in artifact_files:
            artifact_path = Path(str(artifact.get("path") or ""))
            if not artifact_path.exists() or not artifact_path.is_file():
                continue
            db.add(
                ReportFile(
                    report_id=report.id,
                    name=artifact_path.name,
                    path=str(artifact_path),
                    mime_type=_mime_type_for(artifact_path),
                    size_bytes=artifact_path.stat().st_size,
                    checksum=None,
                )
            )
            linked_files += 1

        report.status = "done"
        report.finished_at = datetime.now(timezone.utc)
        report.error_text = None
        db.commit()
        return {"ok": True, "report_id": report.id, "files": linked_files, "path": result.get("path")}
    except Exception as exc:
        db.rollback()
        report = db.get(Report, report_id)
        if report:
            report.status = "failed"
            report.error_text = str(exc)
            report.finished_at = datetime.now(timezone.utc)
            db.commit()
        return {"ok": False, "error": str(exc)}
    finally:
        db.close()
