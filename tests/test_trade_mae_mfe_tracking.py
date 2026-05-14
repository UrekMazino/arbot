from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
EXECUTION = ROOT / "Execution"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(EXECUTION) not in sys.path:
    sys.path.insert(0, str(EXECUTION))

from Execution import func_pair_state as fps  # noqa: E402
from Platform.api.app.services.live_report import _build_trade_rows_from_events  # noqa: E402
from advanced_trade_management import AdvancedTradeManager  # noqa: E402


def _use_temp_pair_state(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True)
    state_file = state_dir / "pair_strategy_state.json"
    monkeypatch.setattr(fps, "_STATE_DIR", state_dir)
    monkeypatch.setattr(fps, "STATE_FILE", state_file)
    return state_file


def test_mfe_updates_when_floating_pnl_improves_and_records_z_guard_floor(tmp_path, monkeypatch):
    _use_temp_pair_state(tmp_path, monkeypatch)

    fps.update_trade_mae_mfe_tracking(0.12, 1.25, 0.55, timestamp=100.0)
    snapshot = fps.update_trade_mae_mfe_tracking(0.46, 0.72, 0.61, timestamp=110.0)

    assert snapshot["max_favorable_pnl_usdt"] == 0.46
    assert snapshot["z_at_max_favorable_pnl"] == 0.72
    assert snapshot["timestamp_at_max_favorable_pnl"] == 110.0
    assert snapshot["guard_floor_at_max_favorable_pnl"] == 0.61


def test_mae_updates_when_floating_pnl_worsens_and_records_z(tmp_path, monkeypatch):
    _use_temp_pair_state(tmp_path, monkeypatch)

    fps.update_trade_mae_mfe_tracking(-0.20, 1.70, 0.50, timestamp=100.0)
    snapshot = fps.update_trade_mae_mfe_tracking(-0.83, 2.45, 0.50, timestamp=130.0)

    assert snapshot["max_adverse_pnl_usdt"] == -0.83
    assert snapshot["z_at_max_adverse_pnl"] == 2.45
    assert snapshot["timestamp_at_max_adverse_pnl"] == 130.0


def test_full_tp_touch_guard_block_and_partial_before_full_flags(tmp_path, monkeypatch):
    _use_temp_pair_state(tmp_path, monkeypatch)

    snapshot = fps.update_trade_mae_mfe_tracking(
        0.30,
        0.22,
        0.75,
        full_tp_touched=True,
        guard_blocked_full_tp=True,
        timestamp=100.0,
    )
    snapshot = fps.update_trade_mae_mfe_tracking(
        0.35,
        0.19,
        0.75,
        full_tp_touched=True,
        guard_blocked_full_tp=True,
        timestamp=101.0,
    )

    assert snapshot["full_tp_touched"] is True
    assert snapshot["guard_blocked_full_tp_count"] == 2

    fps.reset_trade_mae_mfe_tracking()
    snapshot = fps.update_trade_mae_mfe_tracking(
        0.18,
        0.80,
        0.75,
        partial_exit_fired=True,
        timestamp=102.0,
    )
    assert snapshot["partial_exit_before_full_tp"] is True

    fps.reset_trade_mae_mfe_tracking()
    fps.update_trade_mae_mfe_tracking(0.20, 0.22, 0.75, full_tp_touched=True, timestamp=103.0)
    snapshot = fps.update_trade_mae_mfe_tracking(
        0.25,
        0.80,
        0.75,
        partial_exit_fired=True,
        timestamp=104.0,
    )
    assert snapshot["partial_exit_before_full_tp"] is False


def test_trade_close_report_rows_include_mae_mfe_guard_diagnostics():
    row = SimpleNamespace(
        ts=datetime(2026, 5, 14, 5, 30, tzinfo=timezone.utc),
        payload_json={
            "pair": "AAA-USDT-SWAP/BBB-USDT-SWAP",
            "pnl_usdt": "1.23",
            "max_favorable_pnl_usdt": "2.40",
            "max_adverse_pnl_usdt": "-0.50",
            "z_at_max_favorable_pnl": "0.30",
            "z_at_max_adverse_pnl": "2.90",
            "timestamp_at_max_favorable_pnl": "1800000010",
            "timestamp_at_max_adverse_pnl": "1800000020",
            "guard_floor_at_max_favorable_pnl": "0.75",
            "full_tp_touched": "true",
            "guard_blocked_full_tp_count": "3",
            "partial_exit_before_full_tp": "false",
        },
    )

    trade_rows = _build_trade_rows_from_events([row])

    assert trade_rows[0]["max_favorable_pnl_usdt"] == 2.40
    assert trade_rows[0]["max_adverse_pnl_usdt"] == -0.50
    assert trade_rows[0]["z_at_max_favorable_pnl"] == 0.30
    assert trade_rows[0]["z_at_max_adverse_pnl"] == 2.90
    assert trade_rows[0]["timestamp_at_max_favorable_pnl"] == 1800000010.0
    assert trade_rows[0]["timestamp_at_max_adverse_pnl"] == 1800000020.0
    assert trade_rows[0]["guard_floor_at_max_favorable_pnl"] == 0.75
    assert trade_rows[0]["full_tp_touched"] is True
    assert trade_rows[0]["guard_blocked_full_tp_count"] == 3
    assert trade_rows[0]["partial_exit_before_full_tp"] is False


def test_trade_mae_mfe_state_does_not_import_order_execution_modules(tmp_path, monkeypatch):
    state_file = _use_temp_pair_state(tmp_path, monkeypatch)

    fps.update_trade_mae_mfe_tracking(0.1, 1.0, 0.5, timestamp=100.0)

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["trade_mae_mfe"]["max_favorable_pnl_usdt"] == 0.1
    source = Path(fps.__file__).read_text(encoding="utf-8")
    assert "initialise_order_execution" not in source
    assert "place_order" not in source


def test_existing_exit_behavior_is_unchanged_by_read_only_tracking():
    manager = AdvancedTradeManager(
        config={
            "take_profit_z": 0.35,
            "partial_exit_enabled": True,
            "partial_exit_z_threshold": 1.0,
            "trailing_stop_enabled": False,
        }
    )
    manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - 300)

    blocked = manager.update(0.20, floating_pnl_usdt=0.05, min_profit_usdt=0.20)
    allowed = manager.update(0.20, floating_pnl_usdt=0.25, min_profit_usdt=0.20)

    assert blocked["action"] == "HOLD"
    assert blocked["blocked_exit_reason"] == "take_profit"
    assert allowed["action"] == "EXIT"
    assert allowed["reason"] == "take_profit"
