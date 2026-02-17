from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.database import SessionLocal  # noqa: E402
from app.models import Report, ReportFile, Run  # noqa: E402


def generate_report(run_id: str, report_id: str) -> dict:
    """
    Worker entrypoint for V2 report generation.

    This initial implementation links existing v1 report artifacts when present.
    """
    db: Session = SessionLocal()
    try:
        report = db.get(Report, report_id)
        run = db.get(Run, run_id)
        if not report or not run:
            return {"ok": False, "error": "run/report not found"}

        report.status = "running"
        db.commit()

        # Link existing v1 run folder by run_key when available.
        # Example run_key: run_03_20260217_194143
        reports_root = Path(__file__).resolve().parents[3] / "Reports" / "v1"
        linked_files = 0
        if run.run_key:
            run_dir = reports_root / run.run_key
            if run_dir.exists():
                for path in run_dir.iterdir():
                    if path.is_file():
                        rf = ReportFile(
                            report_id=report.id,
                            name=path.name,
                            path=str(path),
                            mime_type=None,
                            size_bytes=path.stat().st_size,
                            checksum=None,
                        )
                        db.add(rf)
                        linked_files += 1

        report.status = "done"
        report.finished_at = datetime.now(timezone.utc)
        report.error_text = None
        db.commit()
        return {"ok": True, "report_id": report.id, "files": linked_files}
    except Exception as exc:
        report = db.get(Report, report_id)
        if report:
            report.status = "failed"
            report.error_text = str(exc)
            report.finished_at = datetime.now(timezone.utc)
            db.commit()
        return {"ok": False, "error": str(exc)}
    finally:
        db.close()

