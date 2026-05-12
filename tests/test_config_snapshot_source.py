from __future__ import annotations

import json
from dataclasses import fields

from core.chart_audit.config_snapshot_source import (
    CONFIG_SOURCE_CURRENT_APPROXIMATE,
    CONFIG_SOURCE_HISTORICAL,
    CURRENT_CONFIG_WARNING,
    config_at,
    current_config_snapshot,
)
from core.chart_audit.replay_snapshot import ReplayConfigSnapshot


def _historical_record(version: str, activated_at: int, entry_z: float) -> dict[str, object]:
    return {
        "config_version": version,
        "activated_at": activated_at,
        "entry_z_threshold": entry_z,
        "exit_z_threshold": 0.35,
        "persistence_candles": 4,
        "max_hold_seconds": 21_600.0,
        "min_zero_crossings": 15,
        "min_liquidity_score": 0.2,
        "max_orderbook_age_ms": 1200.0,
        "max_spread_bps": 6.0,
        "max_slippage_bps": 9.0,
    }


def test_config_at_uses_exact_historical_config_version() -> None:
    result = config_at(
        200,
        historical_configs=[
            _historical_record("v1", 100, 1.9),
            _historical_record("v2", 200, 2.1),
        ],
    )

    assert result.config_version == "v2"
    assert result.config_source == CONFIG_SOURCE_HISTORICAL
    assert result.entry_z_threshold == 2.1
    assert result.warning is None


def test_config_at_uses_latest_historical_config_before_timestamp() -> None:
    result = config_at(
        250,
        historical_configs=[
            _historical_record("v1", 100, 1.9),
            _historical_record("v2", 200, 2.1),
            _historical_record("v3", 300, 2.3),
        ],
    )

    assert result.config_version == "v2"
    assert result.config_source == CONFIG_SOURCE_HISTORICAL
    assert result.entry_z_threshold == 2.1


def test_config_at_falls_back_to_current_approximate_when_historical_unavailable() -> None:
    result = config_at(
        99,
        historical_configs=[_historical_record("v1", 100, 1.9)],
        current_config={
            "signals": {
                "entry_z": 2.2,
                "exit_z": 0.4,
                "min_persist_bars": 3,
                "zero_crossings_min": 8,
            },
            "advanced_ml": {
                "max_book_age_ms": 900.0,
                "wide_spread_bps": 4.5,
            },
            "microstructure": {"max_allowed_slippage_bps": 7.5},
            "exit": {"max_hold_seconds": 7200.0, "min_liquidity_score": 0.15},
        },
        env={},
    )

    assert result.config_version == "current"
    assert result.config_source == CONFIG_SOURCE_CURRENT_APPROXIMATE
    assert result.warning == CURRENT_CONFIG_WARNING
    assert result.entry_z_threshold == 2.2
    assert result.exit_z_threshold == 0.4
    assert result.persistence_candles == 3
    assert result.max_hold_seconds == 7200.0
    assert result.min_zero_crossings == 8
    assert result.min_liquidity_score == 0.15
    assert result.max_orderbook_age_ms == 900.0
    assert result.max_spread_bps == 4.5
    assert result.max_slippage_bps == 7.5


def test_current_config_snapshot_copies_only_replay_fields() -> None:
    result = current_config_snapshot(
        current_config={
            "config_version": "runtime",
            "entry_z_threshold": 2.0,
            "exit_z_threshold": 0.35,
            "persistence_candles": 4,
            "max_hold_seconds": 21_600.0,
            "min_zero_crossings": 15,
            "api_secret": "do-not-copy",
        },
        env={},
    )

    payload = result.__dict__

    assert result.config_version == "runtime"
    assert result.config_source == CONFIG_SOURCE_CURRENT_APPROXIMATE
    assert "api_secret" not in payload
    assert set(payload) == {item.name for item in fields(ReplayConfigSnapshot)}


def test_config_at_reads_jsonl_historical_config_log(tmp_path) -> None:
    log_path = tmp_path / "config_version_log.jsonl"
    records = [
        _historical_record("v1", 100, 1.9),
        _historical_record("v2", 200, 2.1),
    ]
    log_path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")

    result = config_at(250, historical_log_path=log_path)

    assert result.config_version == "v2"
    assert result.config_source == CONFIG_SOURCE_HISTORICAL
    assert result.entry_z_threshold == 2.1


def test_config_at_accepts_materialized_bot_config_style_record() -> None:
    result = config_at(
        200,
        historical_configs=[
            {
                "id": "bot-config-1",
                "created_at": 100,
                "config_snapshot_json": {
                    "signals": {
                        "entry_z": "2.05",
                        "exit_z": "0.30",
                        "min_persist_bars": "5",
                        "zero_crossings_min": "12",
                    },
                    "advanced_ml": {
                        "max_book_age_ms": "1100",
                        "wide_spread_bps": "5.5",
                    },
                    "microstructure": {"max_allowed_slippage_bps": "6.5"},
                    "exit": {"max_hold_seconds": "3600"},
                },
            }
        ],
    )

    assert result.config_version == "bot-config-1"
    assert result.config_source == CONFIG_SOURCE_HISTORICAL
    assert result.entry_z_threshold == 2.05
    assert result.persistence_candles == 5
    assert result.max_hold_seconds == 3600.0
    assert result.max_orderbook_age_ms == 1100.0
    assert result.max_spread_bps == 5.5
    assert result.max_slippage_bps == 6.5


def test_current_fallback_can_use_env_without_silencing_source() -> None:
    result = config_at(
        200,
        historical_configs=[],
        env={
            "STATBOT_ENTRY_Z": "1.95",
            "STATBOT_EXIT_Z": "0.25",
            "STATBOT_MIN_PERSIST_BARS": "2",
            "STATBOT_ADVANCED_ML_MAX_HOLD_SECONDS": "5400",
            "STATBOT_ZERO_CROSSINGS_MIN": "9",
            "STATBOT_EXIT_MIN_LIQUIDITY_SCORE": "0.12",
            "STATBOT_EXIT_MAX_BOOK_AGE_MS": "800",
            "STATBOT_REPLAY_MAX_SPREAD_BPS": "3.5",
            "STATBOT_ADVANCED_ML_MAX_ALLOWED_SLIPPAGE_BPS": "4.5",
        },
    )

    assert result.config_source == CONFIG_SOURCE_CURRENT_APPROXIMATE
    assert result.warning == CURRENT_CONFIG_WARNING
    assert result.entry_z_threshold == 1.95
    assert result.exit_z_threshold == 0.25
    assert result.persistence_candles == 2
    assert result.max_hold_seconds == 5400.0
    assert result.min_zero_crossings == 9
    assert result.min_liquidity_score == 0.12
    assert result.max_orderbook_age_ms == 800.0
    assert result.max_spread_bps == 3.5
    assert result.max_slippage_bps == 4.5
