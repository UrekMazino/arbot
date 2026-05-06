from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STRATEGY_ROOT = ROOT / "Strategy"
if str(STRATEGY_ROOT) not in sys.path:
    sys.path.insert(0, str(STRATEGY_ROOT))

import func_cointegration as fc


BAR_MS = 60_000
BASE_TS = 1_800_000_000_000


@pytest.fixture(autouse=True)
def isolate_strategy_output(monkeypatch, tmp_path):
    strategy_file = tmp_path / "Strategy" / "func_cointegration.py"
    strategy_file.parent.mkdir(parents=True, exist_ok=True)
    strategy_file.write_text("# isolated test module path\n", encoding="utf-8")
    monkeypatch.setattr(fc, "__file__", str(strategy_file))
    monkeypatch.setenv("STATBOT_STRATEGY_REJECT_SAMPLE_PCT", "0")


def _kline(ts: int, close: float) -> dict:
    return {
        "timestamp": str(ts),
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 100.0,
        "volume_ccy": 100.0,
    }


def _symbol(closes: list[float], timestamps: list[int]) -> dict:
    return {
        "symbol_info": {
            "min_sz": 1.0,
            "lot_sz": 1.0,
            "ctVal": 1.0,
            "ctMult": 1.0,
            "ctValCcy": "USDT",
            "maxMktSz": 100000.0,
            "maxStopSz": 100000.0,
        },
        "klines": [_kline(ts, close) for ts, close in zip(timestamps, closes)],
    }


def test_validate_kline_series_drops_forming_epoch_candle():
    rows = [
        _kline(BASE_TS + (idx * BAR_MS), close)
        for idx, close in enumerate([10.0, 10.1, 10.2, 10.3])
    ]

    quality = fc.validate_kline_series(
        rows,
        bar_ms=BAR_MS,
        now_ms=BASE_TS + (3 * BAR_MS) + 30_000,
        closed_candle_only=True,
        max_stale_bars=5,
    )

    assert quality["tier"] == "tier_1"
    assert quality["dropped_forming_candles"] == 1
    assert quality["close_prices"] == [10.0, 10.1, 10.2]
    assert quality["timestamps"] == [BASE_TS + BAR_MS, BASE_TS + (2 * BAR_MS), BASE_TS + (3 * BAR_MS)]
    assert "forming_candle_dropped" in quality["reason_codes"]


def test_validate_kline_series_marks_small_gap_analysis_only():
    timestamps = [BASE_TS, BASE_TS + BAR_MS, BASE_TS + (3 * BAR_MS), BASE_TS + (4 * BAR_MS)]
    rows = [_kline(ts, 10.0 + idx) for idx, ts in enumerate(timestamps)]

    quality = fc.validate_kline_series(
        rows,
        bar_ms=BAR_MS,
        now_ms=BASE_TS + (5 * BAR_MS),
        closed_candle_only=True,
        max_missing_bars=2,
        max_stale_bars=5,
    )

    assert quality["tier"] == "tier_2"
    assert quality["missing_bars"] == 1
    assert "missing_bars" in quality["reason_codes"]
    assert quality["close_prices"] == [10.0, 11.0, 12.0, 13.0]


def test_validate_kline_series_excludes_duplicate_timestamp():
    rows = [
        _kline(BASE_TS, 10.0),
        _kline(BASE_TS, 10.1),
        _kline(BASE_TS + BAR_MS, 10.2),
    ]

    quality = fc.validate_kline_series(
        rows,
        bar_ms=BAR_MS,
        now_ms=BASE_TS + (3 * BAR_MS),
        closed_candle_only=True,
    )

    assert quality["tier"] == "tier_3"
    assert quality["duplicate_timestamps"] == 1
    assert quality["reason_codes"] == ["duplicate_timestamp"]


def test_get_cointegrated_pairs_skips_timestamp_mismatch_before_stats(monkeypatch):
    monkeypatch.setattr(fc, "time_frame", "1m")
    monkeypatch.setattr(fc.time, "time", lambda: (BASE_TS + (6 * BAR_MS)) / 1000)
    monkeypatch.setattr(fc, "_load_restricted_tickers", lambda: set())

    def fail_cointegration(*_args, **_kwargs):
        raise AssertionError("timestamp-misaligned pair should not reach stats")

    monkeypatch.setattr(fc, "calculate_cointegration_from_log", fail_cointegration)

    json_symbols = {
        "AAA-USDT-SWAP": _symbol(
            [10.0, 10.1, 10.2, 10.3],
            [BASE_TS, BASE_TS + BAR_MS, BASE_TS + (2 * BAR_MS), BASE_TS + (3 * BAR_MS)],
        ),
        "BBB-USDT-SWAP": _symbol(
            [11.0, 11.1, 11.2, 11.3],
            [BASE_TS + BAR_MS, BASE_TS + (2 * BAR_MS), BASE_TS + (3 * BAR_MS), BASE_TS + (4 * BAR_MS)],
        ),
    }

    df, summary = fc.get_cointegrated_pairs(
        json_symbols,
        corr_min_override=0.0,
        min_p_value_override=0.0,
        max_p_value_override=0.01,
        min_zero_crossings_override=1,
        write_output=False,
    )

    assert df.empty
    assert summary["total_pairs"] == 1
    assert summary["filtered_breakdown"]["timestamp_alignment"] == 1
    assert summary["timestamp_alignment_filtered"] == 1
    assert summary["data_quality"]["tradable_symbols"] == 2


def test_pair_metric_cache_reuses_only_unchanged_content(monkeypatch):
    monkeypatch.setattr(fc, "time_frame", "1m")
    monkeypatch.setattr(fc, "_load_restricted_tickers", lambda: set())
    monkeypatch.setenv("STATBOT_STRATEGY_PAIR_METRIC_CACHE", "1")

    calls = {"count": 0}

    def fake_cointegration(*_args, **_kwargs):
        calls["count"] += 1
        return 0, 0.5, -1.0, -3.0, 1.0, 0

    monkeypatch.setattr(fc, "calculate_cointegration_from_log", fake_cointegration)
    timestamps = [idx for idx in range(4)]
    json_symbols = {
        "AAA-USDT-SWAP": _symbol([10.0, 10.1, 10.2, 10.3], timestamps),
        "BBB-USDT-SWAP": _symbol([11.0, 11.1, 11.2, 11.3], timestamps),
    }

    _, first_summary = fc.get_cointegrated_pairs(
        json_symbols,
        corr_min_override=0.0,
        min_p_value_override=0.0,
        max_p_value_override=0.01,
        min_zero_crossings_override=1,
        write_output=True,
    )
    assert calls["count"] == 1
    assert first_summary["pair_metric_cache"]["misses"] == 1
    assert first_summary["pair_metric_cache"]["writes"] == 1

    def fail_cointegration(*_args, **_kwargs):
        raise AssertionError("unchanged pair metrics should come from cache")

    monkeypatch.setattr(fc, "calculate_cointegration_from_log", fail_cointegration)
    _, second_summary = fc.get_cointegrated_pairs(
        json_symbols,
        corr_min_override=0.0,
        min_p_value_override=0.0,
        max_p_value_override=0.01,
        min_zero_crossings_override=1,
        write_output=True,
    )
    assert second_summary["pair_metric_cache"]["hits"] == 1
    assert second_summary["pair_metric_cache"]["misses"] == 0

    monkeypatch.setattr(fc, "calculate_cointegration_from_log", fake_cointegration)
    changed_symbols = {
        "AAA-USDT-SWAP": _symbol([10.5, 10.1, 10.2, 10.3], timestamps),
        "BBB-USDT-SWAP": _symbol([11.0, 11.1, 11.2, 11.3], timestamps),
    }
    _, third_summary = fc.get_cointegrated_pairs(
        changed_symbols,
        corr_min_override=0.0,
        min_p_value_override=0.0,
        max_p_value_override=0.01,
        min_zero_crossings_override=1,
        write_output=True,
    )

    assert calls["count"] == 2
    assert third_summary["pair_metric_cache"]["hits"] == 0
    assert third_summary["pair_metric_cache"]["misses"] == 1


def test_tier0_liquidity_prefilter_skips_expensive_stats(monkeypatch):
    monkeypatch.setattr(fc, "time_frame", "1m")
    monkeypatch.setattr(fc, "_load_restricted_tickers", lambda: set())

    def fail_cointegration(*_args, **_kwargs):
        raise AssertionError("pair failing deterministic liquidity floor should skip stats")

    monkeypatch.setattr(fc, "calculate_cointegration_from_log", fail_cointegration)
    timestamps = [idx for idx in range(4)]
    json_symbols = {
        "AAA-USDT-SWAP": _symbol([10.0, 10.1, 10.2, 10.3], timestamps),
        "BBB-USDT-SWAP": _symbol([11.0, 11.1, 11.2, 11.3], timestamps),
    }

    df, summary = fc.get_cointegrated_pairs(
        json_symbols,
        corr_min_override=0.0,
        min_avg_quote_volume_override=2_000.0,
        min_p_value_override=0.0,
        max_p_value_override=0.01,
        min_zero_crossings_override=1,
        write_output=False,
    )

    assert df.empty
    assert summary["filtered_breakdown"]["tier0_liquidity_min"] == 1
    assert summary["validation_tiers"]["tier_0"]["checked_pairs"] == 1
    assert summary["validation_tiers"]["tier_0"]["filtered_pairs"] == 1
    assert summary["validation_tiers"]["tier_2"]["checked_pairs"] == 0
    assert summary["pair_metric_cache"]["misses"] == 0


def test_optional_tier0_vol_ratio_prefilter_is_config_gated(monkeypatch):
    monkeypatch.setattr(fc, "time_frame", "1m")
    monkeypatch.setattr(fc, "_load_restricted_tickers", lambda: set())
    monkeypatch.setenv("STATBOT_STRATEGY_PREFILTER_VOL_RATIO_MAX", "1.1")

    def fail_cointegration(*_args, **_kwargs):
        raise AssertionError("configured volatility-ratio prefilter should skip stats")

    monkeypatch.setattr(fc, "calculate_cointegration_from_log", fail_cointegration)
    timestamps = [idx for idx in range(5)]
    json_symbols = {
        "AAA-USDT-SWAP": _symbol([10.0, 10.1, 10.2, 10.3, 10.4], timestamps),
        "BBB-USDT-SWAP": _symbol([20.0, 21.0, 19.0, 24.0, 18.0], timestamps),
    }

    df, summary = fc.get_cointegrated_pairs(
        json_symbols,
        corr_min_override=0.0,
        min_p_value_override=0.0,
        max_p_value_override=0.01,
        min_zero_crossings_override=1,
        write_output=False,
    )

    assert df.empty
    assert summary["filtered_breakdown"]["tier0_vol_ratio"] == 1
    assert summary["validation_tiers"]["tier_0"]["settings"]["vol_ratio_max"] == 1.1
    assert summary["validation_tiers"]["tier_2"]["checked_pairs"] == 0


def test_accuracy_budget_samples_rejects_without_promoting_them(monkeypatch):
    monkeypatch.setattr(fc, "time_frame", "1m")
    monkeypatch.setattr(fc, "_load_restricted_tickers", lambda: set())
    monkeypatch.setenv("STATBOT_STRATEGY_REJECT_SAMPLE_PCT", "1.0")
    monkeypatch.setenv("STATBOT_STRATEGY_REJECT_SAMPLE_MAX", "10")

    calls = {"count": 0}

    def fake_cointegration(*_args, **_kwargs):
        calls["count"] += 1
        return 1, 0.001, -4.0, -3.0, 1.0, 5

    monkeypatch.setattr(fc, "calculate_cointegration_from_log", fake_cointegration)
    timestamps = [idx for idx in range(5)]
    json_symbols = {
        "AAA-USDT-SWAP": _symbol([10.0, 10.1, 10.2, 10.3, 10.4], timestamps),
        "BBB-USDT-SWAP": _symbol([11.0, 11.1, 11.2, 11.3, 11.4], timestamps),
    }

    df, summary = fc.get_cointegrated_pairs(
        json_symbols,
        corr_min_override=0.0,
        min_avg_quote_volume_override=2_000.0,
        min_p_value_override=0.0,
        max_p_value_override=0.01,
        min_zero_crossings_override=1,
        write_output=False,
    )

    assert df.empty
    assert calls["count"] == 1
    assert summary["pairs_kept"] == 0
    assert summary["validation_tiers"]["tier_2"]["checked_pairs"] == 0
    assert summary["accuracy_budget"]["eligible_rejects"] == 1
    assert summary["accuracy_budget"]["sampled_rejects"] == 1
    assert summary["accuracy_budget"]["missed_cointegrated"] == 1
    assert summary["accuracy_budget"]["missed_with_crossings"] == 1
    assert summary["accuracy_budget"]["missed_stat_candidates"] == 1
    assert summary["accuracy_budget"]["reason_breakdown"]["tier0_liquidity_min"]["sampled_rejects"] == 1
    assert summary["accuracy_budget"]["examples"][0]["pair"] == "AAA-USDT-SWAP/BBB-USDT-SWAP"
