from __future__ import annotations

import json

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db_session, get_user_permission_ids, require_permissions
from ..models import User
from ..services.bot_control import (
    ManualPairSwitchBlocked,
    build_report_run_zip,
    clear_active_pair,
    clear_logs_and_reports,
    delete_log_run,
    get_bot_status,
    get_pair_health_data,
    get_report_run_file,
    get_report_run_summary,
    manual_switch_active_pair,
    resolve_live_stream_target,
    list_log_runs,
    list_report_runs,
    read_env_settings,
    read_run_log,
    start_bot,
    stop_bot,
    tail_run_log,
    update_env_setting,
)
from ..services.cointegrated_pairs import (
    get_cointegrated_pair_detail,
    get_pair_curator_status,
    get_pair_supply_status,
    list_cointegrated_pairs,
    remove_cointegrated_pair,
    set_pair_curator_enabled,
    start_pair_supply,
    stop_pair_supply,
)
from ..services.run_runtime import get_run_runtime_snapshot

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


@router.get("/runs/runtime")
def admin_run_runtime(
    run_key: str | None = Query(default=None),
    _: User = Depends(require_permissions("view_logs", "manage_bot")),
    db: Session = Depends(get_db_session),
):
    return get_run_runtime_snapshot(db, run_key=run_key, include_pair_history=True)


@router.get("/bot/logs/stream")
async def admin_bot_logs_stream(
    request: Request,
    run_key: str | None = Query(default=None),
    _: User = Depends(require_permissions("view_logs")),
):
    """Server-Sent Events endpoint for streaming log updates."""

    async def event_generator():
        import asyncio
        from pathlib import Path

        try:
            target = resolve_live_stream_target(run_key)
        except FileNotFoundError:
            yield "data: {\"error\": \"no log file\"}\n\n"
            return

        log_file = Path(target["log_file"])
        last_pos = log_file.stat().st_size if log_file.exists() else 0
        yield ": connected\n\n"

        while True:
            if await request.is_disconnected():
                return

            try:
                await asyncio.sleep(2)  # Poll every 2 seconds
            except asyncio.CancelledError:
                return

            try:
                if not run_key or str(run_key).strip().lower() == "latest":
                    try:
                        next_target = resolve_live_stream_target(run_key)
                        next_log_file = Path(next_target["log_file"])
                        if next_log_file != log_file:
                            log_file = next_log_file
                            last_pos = 0
                    except FileNotFoundError:
                        yield "data: {\"error\": \"no log file\"}\n\n"
                        return

                if not log_file.exists():
                    yield "data: {\"error\": \"no log file\"}\n\n"
                    return

                current_size = log_file.stat().st_size
                if current_size > last_pos:
                    # Read new content
                    with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                        f.seek(last_pos)
                        new_lines = f.readlines()
                        next_pos = f.tell()

                    if new_lines:
                        # Send last 10 lines as update
                        tail_lines = new_lines[-10:] if len(new_lines) > 10 else new_lines
                        payload = {"lines": [line.rstrip("\n\r") for line in tail_lines]}
                        yield f"data: {json.dumps(payload)}\n\n"
                    last_pos = next_pos

                elif current_size < last_pos:
                    # File was truncated (new run), start from beginning
                    last_pos = 0
                else:
                    # Keep the SSE connection alive between log writes.
                    yield ": ping\n\n"
            except Exception:
                break

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


@router.get("/logs/runs")
def admin_log_runs(
    limit: int = Query(default=100, ge=1, le=500),
    _: User = Depends(require_permissions("view_logs")),
):
    return list_log_runs(limit=limit)


@router.get("/logs/runs/{run_key}")
def admin_log_run_detail(
    run_key: str,
    _: User = Depends(require_permissions("view_logs")),
):
    try:
        return read_run_log(run_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.delete("/logs/runs/{run_key}")
def admin_log_run_delete(
    run_key: str,
    _: User = Depends(require_permissions("manage_logs_reports")),
):
    try:
        return delete_log_run(run_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/reports/runs")
def admin_report_runs(
    limit: int = Query(default=100, ge=1, le=500),
    _: User = Depends(require_permissions("view_reports")),
):
    return list_report_runs(limit=limit)


@router.get("/reports/runs/{run_key}/summary")
def admin_report_run_summary(
    run_key: str,
    _: User = Depends(require_permissions("view_reports")),
    db: Session = Depends(get_db_session),
):
    try:
        return get_report_run_summary(db, run_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/reports/runs/{run_key}/files/{file_name:path}/download")
def admin_report_run_file_download(
    run_key: str,
    file_name: str,
    _: User = Depends(require_permissions("view_reports")),
):
    try:
        file_info = get_report_run_file(run_key, file_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return FileResponse(
        path=file_info["path"],
        filename=file_info["filename"],
        media_type=file_info["media_type"],
    )


@router.get("/reports/runs/{run_key}/download")
def admin_report_run_download(
    run_key: str,
    _: User = Depends(require_permissions("view_reports")),
):
    try:
        payload, filename = build_report_run_zip(run_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(iter([payload]), media_type="application/zip", headers=headers)


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
def admin_pairs_health(
    _: User = Depends(require_permissions("view_pair_universe", "view_logs", "manage_bot", "switch_active_pair")),
):
    return get_pair_health_data()


@router.get("/cointegrated-pairs")
def admin_cointegrated_pairs(
    limit: int = Query(default=500, ge=1, le=1000),
    _: User = Depends(require_permissions("view_pair_universe", "view_dashboard")),
):
    try:
        return list_cointegrated_pairs(limit=limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.get("/cointegrated-pairs/detail")
def admin_cointegrated_pair_detail(
    sym_1: str = Query(..., min_length=1),
    sym_2: str = Query(..., min_length=1),
    limit: int = Query(default=720, ge=50, le=2000),
    _: User = Depends(require_permissions("view_pair_universe", "view_dashboard")),
):
    try:
        return get_cointegrated_pair_detail(sym_1=sym_1, sym_2=sym_2, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.delete("/cointegrated-pairs")
def admin_remove_cointegrated_pair(
    payload: dict = Body(default_factory=dict),
    user: User = Depends(require_permissions("manage_pair_supply", "manage_bot")),
):
    try:
        return remove_cointegrated_pair(
            sym_1=str(payload.get("sym_1") or ""),
            sym_2=str(payload.get("sym_2") or ""),
            requested_by=user.email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.get("/cointegrated-pairs/supply/status")
def admin_cointegrated_pair_supply_status(
    _: User = Depends(require_permissions("view_pair_universe", "view_dashboard")),
):
    return get_pair_supply_status()


@router.get("/cointegrated-pairs/curator/status")
def admin_cointegrated_pair_curator_status(
    _: User = Depends(require_permissions("view_pair_universe", "view_dashboard")),
):
    return get_pair_curator_status()


@router.post("/cointegrated-pairs/curator/enabled")
def admin_cointegrated_pair_curator_enabled(
    payload: dict = Body(default_factory=dict),
    user: User = Depends(require_permissions("manage_pair_supply", "manage_bot")),
):
    return set_pair_curator_enabled(bool(payload.get("enabled")), requested_by=user.email)


@router.post("/cointegrated-pairs/supply/start")
def admin_cointegrated_pair_supply_start(
    user: User = Depends(require_permissions("manage_pair_supply", "manage_bot")),
):
    return start_pair_supply(requested_by=user.email)


@router.post("/cointegrated-pairs/supply/stop")
def admin_cointegrated_pair_supply_stop(
    user: User = Depends(require_permissions("manage_pair_supply", "manage_bot")),
):
    return stop_pair_supply(requested_by=user.email)


@router.post("/pairs/active/clear")
def admin_clear_active_pair(user: User = Depends(require_permissions("switch_active_pair", "manage_bot"))):
    try:
        return clear_active_pair(requested_by=user.email)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/pairs/active/switch")
def admin_manual_switch_active_pair(
    payload: dict = Body(default_factory=dict),
    user: User = Depends(require_permissions("switch_active_pair", "manage_bot")),
):
    try:
        return manual_switch_active_pair(
            sym_1=str(payload.get("sym_1") or payload.get("ticker_1") or ""),
            sym_2=str(payload.get("sym_2") or payload.get("ticker_2") or ""),
            requested_by=user.email,
        )
    except ManualPairSwitchBlocked as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.result.get("detail")) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/logs/clear")
def admin_logs_clear(
    keep_latest: bool = Query(default=False),
    _: User = Depends(require_permissions("manage_logs_reports")),
):
    """Clear log and report data, optionally preserving the newest run when requested."""
    return clear_logs_and_reports(keep_latest=keep_latest)
