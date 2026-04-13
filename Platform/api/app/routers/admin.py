from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from ..deps import get_current_user, get_user_permission_ids, require_permissions
from ..models import User
from ..services.bot_control import (
    clear_logs_and_reports,
    get_bot_status,
    get_pair_health_data,
    list_log_runs,
    list_report_runs,
    read_env_settings,
    start_bot,
    stop_bot,
    tail_run_log,
    update_env_setting,
)

router = APIRouter(prefix="/admin", tags=["admin"])
API_ENV_KEYS = {"OKX_API_KEY", "OKX_API_SECRET", "OKX_FLAG", "OKX_PASSPHRASE"}


def _filter_env_settings(values: dict[str, str], user_permissions: set[str]) -> dict[str, str]:
    filtered: dict[str, str] = {}
    for key, value in values.items():
        if key in API_ENV_KEYS:
            if "manage_api" in user_permissions:
                filtered[key] = value
            continue
        if "edit_settings" in user_permissions:
            filtered[key] = value
    return filtered


def _require_any_settings_permission(user_permissions: set[str]) -> None:
    if user_permissions.intersection({"edit_settings", "manage_api"}):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


@router.get("/bot/status")
def admin_bot_status(_: User = Depends(require_permissions("view_logs", "manage_bot"))):
    return get_bot_status()


@router.post("/bot/start")
def admin_bot_start(user: User = Depends(require_permissions("manage_bot"))):
    return start_bot(requested_by=user.email)


@router.post("/bot/stop")
def admin_bot_stop(user: User = Depends(require_permissions("manage_bot"))):
    return stop_bot(requested_by=user.email)


@router.get("/bot/logs/tail")
def admin_bot_logs_tail(
    run_key: str | None = Query(default=None),
    lines: int = Query(default=400, ge=10, le=2000),
    _: User = Depends(require_permissions("view_logs")),
):
    return tail_run_log(run_key=run_key, lines=lines)


@router.get("/logs/runs")
def admin_log_runs(
    limit: int = Query(default=100, ge=1, le=500),
    _: User = Depends(require_permissions("view_logs")),
):
    return list_log_runs(limit=limit)


@router.get("/reports/runs")
def admin_report_runs(
    limit: int = Query(default=100, ge=1, le=500),
    _: User = Depends(require_permissions("view_reports")),
):
    return list_report_runs(limit=limit)


@router.get("/settings/env")
def admin_env_settings(user: User = Depends(get_current_user)):
    user_permissions = get_user_permission_ids(user)
    _require_any_settings_permission(user_permissions)
    return {"path": "Execution/.env", "values": _filter_env_settings(read_env_settings(), user_permissions)}


@router.put("/settings/env/{key}")
def admin_env_settings_update(
    key: str,
    payload: dict = Body(default_factory=dict),
    user: User = Depends(get_current_user),
):
    user_permissions = get_user_permission_ids(user)
    normalized_key = str(key or "").strip()
    if normalized_key in API_ENV_KEYS:
        if "manage_api" not in user_permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    elif "edit_settings" not in user_permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    value = payload.get("value", "")
    result = update_env_setting(key=key, value=str(value))
    result["values"] = _filter_env_settings(read_env_settings(), user_permissions)
    return result


@router.get("/pairs/health")
def admin_pairs_health(_: User = Depends(require_permissions("view_logs", "manage_bot"))):
    return get_pair_health_data()


@router.post("/logs/clear")
def admin_logs_clear(
    keep_latest: bool = Query(default=True),
    user: User = Depends(require_permissions("manage_bot")),
):
    """Clear old log and report directories."""
    return clear_logs_and_reports(keep_latest=keep_latest)
