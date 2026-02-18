from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Query

from ..deps import require_superuser
from ..models import User
from ..services.bot_control import (
    get_bot_status,
    list_log_runs,
    list_report_runs,
    read_env_settings,
    start_bot,
    stop_bot,
    tail_run_log,
    update_env_setting,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/bot/status")
def admin_bot_status(_: User = Depends(require_superuser)):
    return get_bot_status()


@router.post("/bot/start")
def admin_bot_start(user: User = Depends(require_superuser)):
    return start_bot(requested_by=user.email)


@router.post("/bot/stop")
def admin_bot_stop(user: User = Depends(require_superuser)):
    return stop_bot(requested_by=user.email)


@router.get("/bot/logs/tail")
def admin_bot_logs_tail(
    run_key: str | None = Query(default=None),
    lines: int = Query(default=400, ge=10, le=2000),
    _: User = Depends(require_superuser),
):
    return tail_run_log(run_key=run_key, lines=lines)


@router.get("/logs/runs")
def admin_log_runs(
    limit: int = Query(default=100, ge=1, le=500),
    _: User = Depends(require_superuser),
):
    return list_log_runs(limit=limit)


@router.get("/reports/runs")
def admin_report_runs(
    limit: int = Query(default=100, ge=1, le=500),
    _: User = Depends(require_superuser),
):
    return list_report_runs(limit=limit)


@router.get("/settings/env")
def admin_env_settings(_: User = Depends(require_superuser)):
    return {"path": "Execution/.env", "values": read_env_settings()}


@router.put("/settings/env/{key}")
def admin_env_settings_update(
    key: str,
    payload: dict = Body(default_factory=dict),
    _: User = Depends(require_superuser),
):
    value = payload.get("value", "")
    result = update_env_setting(key=key, value=str(value))
    result["values"] = read_env_settings()
    return result
