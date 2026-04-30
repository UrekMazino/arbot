from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXECUTION_DIR = ROOT / "Execution"
if str(EXECUTION_DIR) not in sys.path:
    sys.path.insert(0, str(EXECUTION_DIR))

import main_execution as me


def _write_supply_state(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_pair_supply_scan_progress_reads_active_price_history(monkeypatch, tmp_path):
    log_path = tmp_path / "pair_supply_scheduler.log"
    log_path.write_text(
        "\n".join(
            [
                "2026-04-22T01:22:49.227768+00:00 pair_supply scan_start",
                "[###---------------------] 16/122 ACT-USDT-SWAP | OK 10080 candles | stored 16/122",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(me, "PAIR_SUPPLY_LOG_FILE", log_path)

    progress = me._read_pair_supply_scan_progress({"log_file": str(log_path)})

    assert progress["known"] is True
    assert progress["active"] is True
    assert progress["current"] == 16
    assert progress["total"] == 122
    assert progress["phase"] == "fetching price history"


def test_pair_supply_scan_progress_ignores_timestamp_glued_to_stored_total(monkeypatch, tmp_path):
    log_path = tmp_path / "pair_supply_scheduler.log"
    log_path.write_text(
        "\n".join(
            [
                "2026-04-22T01:22:49.227768+00:00 pair_supply scan_start",
                "[##########--------------] 54/122 HBAR-USDT-SWAP | OK 10080 candles | stored 54/1222026-04-22 09:46:52,746 INFO next log",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(me, "PAIR_SUPPLY_LOG_FILE", log_path)

    progress = me._read_pair_supply_scan_progress({"log_file": str(log_path)})

    assert progress["current"] == 54
    assert progress["total"] == 122


def test_pair_supply_scan_progress_detects_watched_completion_with_next_scan_active(monkeypatch, tmp_path):
    log_path = tmp_path / "pair_supply_scheduler.log"
    watched_start = "2026-04-22T01:00:00.000000+00:00"
    log_path.write_text(
        "\n".join(
            [
                f"{watched_start} pair_supply scan_start",
                "[########################] 122/122 HOOD-USDT-SWAP | OK 10080 candles | stored 122/122",
                "2026-04-22T02:00:00.000000+00:00 pair_supply scan_end exit_code=0 elapsed_seconds=3600.0",
                "2026-04-22T02:00:00.100000+00:00 pair_supply scan_start",
                "[------------------------] 1/122 SOL-USDT-SWAP | OK 10080 candles | stored 1/122",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(me, "PAIR_SUPPLY_LOG_FILE", log_path)

    progress = me._read_pair_supply_scan_progress(
        {"log_file": str(log_path)},
        watch_started_at=watched_start,
    )

    assert progress["active"] is True
    assert progress["watched_completed"] is True
    assert progress["latest_start_at"] == "2026-04-22T02:00:00.100000+00:00"
    assert progress["current"] == 1
    assert progress["total"] == 122


def test_pair_supply_scan_progress_reports_pair_doctor_confirmation(monkeypatch, tmp_path):
    log_path = tmp_path / "pair_supply_scheduler.log"
    log_path.write_text(
        "\n".join(
            [
                "2026-04-22T01:22:49.227768+00:00 pair_supply scan_start",
                "[########################] 122/122 HOOD-USDT-SWAP | OK 10080 candles | stored 122/122",
                "Price history saved: output/1_price_list.json",
                "2026-04-22T01:40:00.000000+00:00 pair_supply curator_start",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(me, "PAIR_SUPPLY_LOG_FILE", log_path)

    progress = me._read_pair_supply_scan_progress({"log_file": str(log_path)})

    assert progress["active"] is True
    assert progress["phase"] == "pair doctor confirming"


def test_execution_defers_to_fresh_pair_supply_start_request(monkeypatch, tmp_path):
    state_path = tmp_path / "pair_supply_control.json"
    now = datetime.now(timezone.utc).isoformat()
    _write_supply_state(
        state_path,
        {
            "running": False,
            "desired_running": True,
            "detail": "start_requested",
            "process_mode": "runner",
            "process_owner": "pair-supply-runner",
            "request_updated_at": now,
        },
    )

    monkeypatch.setattr(me, "PAIR_SUPPLY_STATE_FILE", state_path)
    monkeypatch.setattr(me.subprocess, "call", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()))

    status = me._get_pair_supply_runtime_status()

    assert status["running"] is False
    assert status["desired_running"] is True
    assert status["defer_to_supply"] is True
    assert me._run_strategy_refresh() is False


def test_execution_trusts_fresh_remote_pair_supply_state_without_local_pid(monkeypatch, tmp_path):
    state_path = tmp_path / "pair_supply_control.json"
    now = datetime.now(timezone.utc).isoformat()
    _write_supply_state(
        state_path,
        {
            "running": True,
            "desired_running": True,
            "pid": 12345,
            "detail": "started",
            "process_owner": "pair-supply-runner",
            "updated_at": now,
        },
    )

    monkeypatch.setenv("STATBOT_PROCESS_OWNER", "bot-runner")
    monkeypatch.setattr(me, "PAIR_SUPPLY_STATE_FILE", state_path)
    monkeypatch.setattr(me, "_pid_matches_pair_supply", lambda _pid: False)

    status = me._get_pair_supply_runtime_status()

    assert status["running"] is True
    assert status["defer_to_supply"] is True


def test_execution_trusts_existing_supplied_pair_universe_rows_when_runner_stopped(monkeypatch, tmp_path):
    state_path = tmp_path / "pair_supply_control.json"
    csv_path = tmp_path / "2_cointegrated_pairs.csv"
    csv_path.write_text(
        "sym_1,sym_2,avg_quote_volume_1,avg_quote_volume_2,pair_liquidity_min\n"
        + "\n".join(
            [
                f"AAA{i}-USDT-SWAP,BBB{i}-USDT-SWAP,10000,10000,10000"
                for i in range(8)
            ]
        ),
        encoding="utf-8",
    )
    old = (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat()
    _write_supply_state(
        state_path,
        {
            "running": False,
            "desired_running": False,
            "detail": "stopped",
            "updated_at": old,
            "status": {
                "canonical_rows": 8,
                "canonical_path": str(csv_path),
                "accumulated_supply": True,
            },
        },
    )

    monkeypatch.setattr(me, "PAIR_SUPPLY_STATE_FILE", state_path)
    monkeypatch.setattr(me, "PAIR_SUPPLY_STATUS_FILE", tmp_path / "missing_status.json")

    status = me._get_pair_supply_runtime_status()

    assert status["defer_to_supply"] is False
    assert status["canonical_rows"] == 8
    assert me._should_trust_pair_universe_candidates(csv_path) is True


def test_pair_curator_readiness_requires_matching_generation(monkeypatch, tmp_path):
    csv_path = tmp_path / "2_cointegrated_pairs.csv"
    csv_path.write_text(
        "sym_1,sym_2,avg_quote_volume_1,avg_quote_volume_2,pair_liquidity_min\n"
        "AAA-USDT-SWAP,BBB-USDT-SWAP,10000,10000,10000\n",
        encoding="utf-8",
    )
    status_path = tmp_path / "2_cointegrated_pairs_status.json"
    status_path.write_text(
        json.dumps(
            {
                "pair_universe_generation": "generation-new",
                "canonical_rows": 1,
                "curator_ready": False,
            }
        ),
        encoding="utf-8",
    )
    report_path = tmp_path / "pair_universe_curator.json"
    report_path.write_text(
        json.dumps(
            {
                "source_generation": "generation-old",
                "pairs": {
                    "AAA-USDT-SWAP/BBB-USDT-SWAP": {
                        "sym_1": "AAA-USDT-SWAP",
                        "sym_2": "BBB-USDT-SWAP",
                        "status": "healthy",
                        "recommendation": "promote",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("STATBOT_SWITCH_REQUIRE_CURATOR_HEALTHY", "1")
    monkeypatch.setattr(me, "PAIR_SUPPLY_STATUS_FILE", status_path)
    monkeypatch.setattr(me, "PAIR_CURATOR_REPORT_FILE", report_path)

    ready, detail = me._pair_curator_readiness(csv_path=csv_path)

    assert ready is False
    assert "stale" in detail

    status_path.write_text(
        json.dumps(
            {
                "pair_universe_generation": "generation-new",
                "canonical_rows": 1,
                "curator_ready": True,
                "curator_generation": "generation-new",
            }
        ),
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(
            {
                "source_generation": "generation-new",
                "pairs": {
                    "AAA-USDT-SWAP/BBB-USDT-SWAP": {
                        "sym_1": "AAA-USDT-SWAP",
                        "sym_2": "BBB-USDT-SWAP",
                        "status": "healthy",
                        "recommendation": "promote",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    ready, detail = me._pair_curator_readiness(csv_path=csv_path)

    assert ready is True
    assert "matches" in detail


def test_no_switch_candidate_wait_context_names_curator_pending(monkeypatch, tmp_path):
    csv_path = tmp_path / "2_cointegrated_pairs.csv"
    csv_path.write_text(
        "sym_1,sym_2,avg_quote_volume_1,avg_quote_volume_2,pair_liquidity_min\n"
        + "\n".join(
            [
                f"AAA{i}-USDT-SWAP,BBB{i}-USDT-SWAP,10000,10000,10000"
                for i in range(8)
            ]
        ),
        encoding="utf-8",
    )
    report_path = tmp_path / "pair_universe_curator.json"
    report_path.write_text(
        json.dumps(
            {
                "source_generation": "generation-old",
                "pairs": {
                    "AAA0-USDT-SWAP/BBB0-USDT-SWAP": {
                        "sym_1": "AAA0-USDT-SWAP",
                        "sym_2": "BBB0-USDT-SWAP",
                        "status": "healthy",
                        "recommendation": "promote",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("STATBOT_SWITCH_REQUIRE_CURATOR_HEALTHY", "1")
    monkeypatch.setattr(me, "PAIR_CURATOR_REPORT_FILE", report_path)

    context, detail = me._pair_supply_wait_context(
        {"status": {"pair_universe_generation": "generation-new", "curator_ready": False}},
        "no_switch_candidate",
        csv_path=csv_path,
    )

    assert context == "curator_pending_or_stale"
    assert "stale" in detail


def test_execution_does_not_defer_to_stale_pair_supply_request(monkeypatch, tmp_path):
    state_path = tmp_path / "pair_supply_control.json"
    old = (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat()
    _write_supply_state(
        state_path,
        {
            "running": False,
            "desired_running": True,
            "detail": "start_requested",
            "process_mode": "runner",
            "process_owner": "pair-supply-runner",
            "request_updated_at": old,
            "runner_heartbeat_at": old,
            "updated_at": old,
        },
    )

    monkeypatch.setattr(me, "PAIR_SUPPLY_STATE_FILE", state_path)

    status = me._get_pair_supply_runtime_status()

    assert status["running"] is False
    assert status["defer_to_supply"] is False


def test_active_pair_universe_block_detects_pruned_pair(monkeypatch, tmp_path):
    csv_path = tmp_path / "2_cointegrated_pairs.csv"
    csv_path.write_text(
        "sym_1,sym_2,avg_quote_volume_1,avg_quote_volume_2,pair_liquidity_min\n"
        "CCC-USDT-SWAP,DDD-USDT-SWAP,10000,10000,10000\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(me, "ticker_1", "AAA-USDT-SWAP")
    monkeypatch.setattr(me, "ticker_2", "BBB-USDT-SWAP")

    reason, detail = me._get_active_pair_universe_block(csv_path, require_curator=False)

    assert reason == "pair_universe_pruned"
    assert "not in the supplied Pair Universe" in detail


def test_active_pair_universe_block_detects_unhealthy_curator_status(monkeypatch, tmp_path):
    csv_path = tmp_path / "2_cointegrated_pairs.csv"
    csv_path.write_text(
        "sym_1,sym_2,avg_quote_volume_1,avg_quote_volume_2,pair_liquidity_min\n"
        "AAA-USDT-SWAP,BBB-USDT-SWAP,10000,10000,10000\n",
        encoding="utf-8",
    )
    report_path = tmp_path / "pair_universe_curator.json"
    report_path.write_text(
        json.dumps(
            {
                "pairs": {
                    "AAA-USDT-SWAP/BBB-USDT-SWAP": {
                        "sym_1": "AAA-USDT-SWAP",
                        "sym_2": "BBB-USDT-SWAP",
                        "status": "watch",
                        "recommendation": "watch",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(me, "PAIR_CURATOR_REPORT_FILE", report_path)
    monkeypatch.setattr(me, "ticker_1", "AAA-USDT-SWAP")
    monkeypatch.setattr(me, "ticker_2", "BBB-USDT-SWAP")

    reason, detail = me._get_active_pair_universe_block(csv_path, require_curator=True)

    assert reason == "pair_universe_pruned"
    assert "status=watch recommendation=watch" in detail


def test_pruned_active_pair_switches_only_when_flat(monkeypatch, tmp_path):
    csv_path = tmp_path / "2_cointegrated_pairs.csv"
    csv_path.write_text(
        "sym_1,sym_2,avg_quote_volume_1,avg_quote_volume_2,pair_liquidity_min\n"
        "CCC-USDT-SWAP,DDD-USDT-SWAP,10000,10000,10000\n",
        encoding="utf-8",
    )
    calls = []

    monkeypatch.setattr(me, "ticker_1", "AAA-USDT-SWAP")
    monkeypatch.setattr(me, "ticker_2", "BBB-USDT-SWAP")
    monkeypatch.setattr(me, "lock_on_pair", False)
    monkeypatch.setattr(me, "set_last_switch_reason", lambda reason: calls.append(("reason", reason)))
    monkeypatch.setattr(
        me,
        "_switch_to_next_pair",
        lambda health_score=None, switch_reason="health": calls.append((health_score, switch_reason))
        or me.SWITCH_RESULT_SWITCHED,
    )

    result = me._maybe_switch_pruned_active_pair(
        csv_path,
        is_manage_new_trades=True,
        account_flat=True,
        account_flat_blockers=[],
    )

    assert result == me.SWITCH_RESULT_SWITCHED
    assert ("reason", "pair_universe_pruned") in calls
    assert (0, "pair_universe_pruned") in calls


def test_pruned_active_pair_defers_when_not_flat(monkeypatch, tmp_path):
    csv_path = tmp_path / "2_cointegrated_pairs.csv"
    csv_path.write_text(
        "sym_1,sym_2,avg_quote_volume_1,avg_quote_volume_2,pair_liquidity_min\n"
        "CCC-USDT-SWAP,DDD-USDT-SWAP,10000,10000,10000\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(me, "ticker_1", "AAA-USDT-SWAP")
    monkeypatch.setattr(me, "ticker_2", "BBB-USDT-SWAP")
    monkeypatch.setattr(me, "lock_on_pair", False)
    monkeypatch.setattr(me, "_emit_pair_switch_blocked", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        me,
        "_switch_to_next_pair",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not switch")),
    )

    result = me._maybe_switch_pruned_active_pair(
        csv_path,
        is_manage_new_trades=False,
        account_flat=False,
        account_flat_blockers=["open order exists"],
    )

    assert result == me.SWITCH_RESULT_BLOCKED


def test_trade_close_result_uses_verified_entry_to_post_close_equity():
    result = me._select_trade_close_result(
        entry_equity=100.0,
        post_close_equity=101.25,
        pre_close_equity_change=None,
        starting_equity=99.0,
        position_pnl=-5.0,
    )

    assert result["pnl"] == pytest.approx(1.25)
    assert result["basis"] == "entry_to_post_close_equity"
    assert result["label"] == "WIN"
    assert result["verified"] is True
    assert result["record_history"] is True


def test_trade_close_result_quarantines_restart_close_with_session_equity_delta():
    result = me._select_trade_close_result(
        entry_equity=None,
        post_close_equity=2747.85,
        pre_close_equity_change=None,
        starting_equity=2748.00,
        position_pnl=0.82,
    )

    assert result["pnl"] == pytest.approx(-0.15)
    assert result["basis"] == "session_equity_delta_unverified"
    assert result["label"] == "UNVERIFIED"
    assert result["verified"] is False
    assert result["record_history"] is False


def test_trade_close_result_keeps_position_pnl_unverified_when_equity_missing():
    result = me._select_trade_close_result(
        entry_equity=None,
        post_close_equity=None,
        pre_close_equity_change=None,
        starting_equity=None,
        position_pnl=0.82,
    )

    assert result["pnl"] == pytest.approx(0.82)
    assert result["basis"] == "position_pnl_unverified"
    assert result["label"] == "UNVERIFIED"
    assert result["verified"] is False
    assert result["record_history"] is False
