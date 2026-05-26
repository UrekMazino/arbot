import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from entry_safety_gate import (  # noqa: E402
    EntrySafetyGateConfig,
    clear_entry_safety_gate_state,
    evaluate_entry_safety_gate,
    record_entry_coint_pvalue,
    record_entry_safety_pair_event,
)
import func_trade_management as ftm  # noqa: E402


def _config(**overrides):
    values = {
        "enabled": True,
        "min_cointegration_component": 20.0,
        "min_correlation_component": 7.0,
        "block_liquidity_floor": True,
        "block_risk_off_thin_liquidity": True,
        "block_risk_off_vol_shock": True,
        "block_trending_ml": True,
        "block_statarb_mr_in_trend": True,
        "max_break_risk": 0.12,
        "cointegration_watch_cooldown_seconds": 1800.0,
        "cointegration_lost_cooldown_seconds": 3600.0,
        "cointegration_broken_cooldown_seconds": 7200.0,
        "watch_timeout_cooldown_seconds": 3600.0,
        "coint_stability_enabled": True,
        "coint_stability_window": 5,
        "coint_stability_slope_max": 0.020,
        "coint_stability_min_sample_interval_seconds": 60.0,
    }
    values.update(overrides)
    return EntrySafetyGateConfig(**values)


def _quality(**components):
    defaults = {
        "cointegration": 24.0,
        "correlation": 9.0,
        "liquidity": 14.0,
    }
    defaults.update(components)
    return SimpleNamespace(components=defaults)


def _good_metrics():
    return {
        "coint_flag": 1,
        "coint_health": "healthy",
        "p_value": 0.01,
        "correlation": 0.9,
        "zero_crossings": 25,
    }


def _decision(**kwargs):
    cfg = kwargs.pop("config", _config())
    now = kwargs.pop("now", 1000.0)
    metrics = kwargs.pop("metrics", _good_metrics())
    quality_decision = kwargs.pop("quality_decision", _quality())
    return evaluate_entry_safety_gate(
        pair="AAA-USDT-SWAP/BBB-USDT-SWAP",
        metrics=metrics,
        quality_decision=quality_decision,
        ratio_long=10.0,
        ratio_short=10.0,
        min_liquidity_ratio=5.0,
        config=cfg,
        now=now,
        **kwargs,
    )


def setup_function():
    clear_entry_safety_gate_state()


def test_gate_blocks_recent_cointegration_lost_pair():
    cfg = _config()
    record_entry_safety_pair_event(
        "AAA-USDT-SWAP/BBB-USDT-SWAP",
        "cointegration_lost",
        now=100.0,
        config=cfg,
    )

    decision = _decision(config=cfg, now=101.0)

    assert not decision.passed
    assert "recent_cointegration_lost_cooldown" in decision.reasons
    assert decision.cooldown_remaining_seconds is not None


def test_gate_blocks_recent_cointegration_watch_timeout_pair():
    cfg = _config()
    record_entry_safety_pair_event(
        "AAA-USDT-SWAP/BBB-USDT-SWAP",
        "cointegration_watch_timeout",
        now=100.0,
        config=cfg,
    )

    decision = _decision(config=cfg, now=101.0)

    assert not decision.passed
    assert "recent_cointegration_watch_timeout_cooldown" in decision.reasons


def test_gate_blocks_current_watch_or_broken_coint_state():
    watch_decision = _decision(metrics={"coint_flag": 0, "coint_health": "watch"})
    broken_decision = _decision(metrics={"coint_flag": 0, "coint_health": "broken"})

    assert not watch_decision.passed
    assert "cointegration_watch" in watch_decision.reasons
    assert not broken_decision.passed
    assert "cointegration_broken" in broken_decision.reasons


def test_gate_blocks_low_cointegration_component_score():
    decision = _decision(quality_decision=_quality(cointegration=19.99))

    assert not decision.passed
    assert "cointegration_component_below_threshold" in decision.reasons


def test_gate_blocks_low_correlation_component_score():
    decision = _decision(quality_decision=_quality(correlation=6.99))

    assert not decision.passed
    assert "correlation_component_below_threshold" in decision.reasons


def test_gate_blocks_risk_off_thin_liquidity():
    regime = SimpleNamespace(regime="RISK_OFF", reason_codes=["thin_liquidity"])

    decision = _decision(regime_decision=regime)

    assert not decision.passed
    assert "risk_off_thin_liquidity" in decision.reasons


def test_gate_blocks_risk_off_vol_shock():
    regime = SimpleNamespace(regime="RISK_OFF", reason_codes=["vol_shock"])

    decision = _decision(regime_decision=regime)

    assert not decision.passed
    assert "risk_off_vol_shock" in decision.reasons


def test_gate_blocks_ml_trending_or_high_break_risk():
    trending = SimpleNamespace(regime=SimpleNamespace(value="TRENDING"), break_risk=0.05)
    high_break = SimpleNamespace(regime=SimpleNamespace(value="RANGE"), break_risk=0.121)

    trending_decision = _decision(advanced_regime_result=trending)
    high_break_decision = _decision(advanced_regime_result=high_break)

    assert not trending_decision.passed
    assert "advanced_ml_trending" in trending_decision.reasons
    assert not high_break_decision.passed
    assert "advanced_ml_break_risk_high" in high_break_decision.reasons


def test_gate_allows_good_range_mean_reverting_pair():
    regime = SimpleNamespace(regime="RANGE", reason_codes=[])
    strategy = SimpleNamespace(active_strategy="STATARB_MR", reason_codes=[])
    advanced = SimpleNamespace(regime=SimpleNamespace(value="RANGE"), break_risk=0.05)

    decision = _decision(
        regime_decision=regime,
        strategy_decision=strategy,
        advanced_regime_result=advanced,
    )

    assert decision.passed
    assert decision.reason == "entry_safety_gate_passed"


def test_cooldown_expires_and_pair_can_pass_again():
    cfg = _config(cointegration_lost_cooldown_seconds=10.0)
    record_entry_safety_pair_event(
        "AAA-USDT-SWAP/BBB-USDT-SWAP",
        "cointegration_lost",
        now=100.0,
        config=cfg,
    )

    blocked = _decision(config=cfg, now=105.0)
    passed = _decision(config=cfg, now=111.0)

    assert not blocked.passed
    assert passed.passed


def test_disabled_gate_preserves_current_behavior():
    decision = _decision(
        config=_config(enabled=False),
        metrics={"coint_flag": 0, "coint_health": "broken"},
        quality_decision=_quality(cointegration=0.0, correlation=0.0),
    )

    assert decision.passed
    assert decision.reason == "entry_safety_gate_disabled"


def test_block_payload_contains_dashboard_ready_fields():
    decision = _decision(quality_decision=_quality(cointegration=10.0))
    payload = decision.to_payload()

    assert payload["entry_gate_passed"] is False
    assert payload["entry_gate_block_reason"]
    assert payload["entry_gate_component_scores"]["cointegration"] == 10.0
    assert "config_thresholds" in payload


def test_helper_does_not_import_order_execution_modules():
    import entry_safety_gate

    imported_names = set(vars(entry_safety_gate))
    assert "initialise_order_execution" not in imported_names
    assert "place_entry_with_stop" not in imported_names


def test_entry_safety_gate_emit_event_contains_reason(monkeypatch):
    captured = {}

    def fake_emit_event(event_type, payload=None, severity="info", logger=None):
        captured["event_type"] = event_type
        captured["payload"] = payload or {}
        captured["severity"] = severity
        return True

    monkeypatch.setattr(ftm, "emit_event", fake_emit_event)
    decision = _decision(quality_decision=_quality(cointegration=10.0))

    ftm._emit_entry_safety_gate(decision, pair="AAA/BBB", strategy="STATARB_MR", regime="RANGE", signal="BUY_SPREAD")

    assert captured["event_type"] == "entry_safety_gate"
    assert captured["severity"] == "warn"
    assert captured["payload"]["reason"] == "cointegration_component_below_threshold"
    assert captured["payload"]["entry_gate_block_reason"] == "cointegration_component_below_threshold"


# ---------------------------------------------------------------------------
# Patch 4 — Regime-Aligned Mean Reversion Safety (STATARB_MR + TREND block)
# ---------------------------------------------------------------------------

def _trend_regime():
    return SimpleNamespace(regime="TREND", reason_codes=["trend_continuation"])


def _range_regime():
    return SimpleNamespace(regime="RANGE", reason_codes=[])


def _statarb_mr_strategy():
    return SimpleNamespace(active_strategy="STATARB_MR", desired_strategy="STATARB_MR", reason_codes=[])


def _other_strategy(name="TREND_SPREAD"):
    return SimpleNamespace(active_strategy=name, desired_strategy=name, reason_codes=[])


def test_statarb_mr_in_trend_is_blocked():
    decision = _decision(
        regime_decision=_trend_regime(),
        strategy_decision=_statarb_mr_strategy(),
    )
    assert not decision.passed
    assert "statarb_mr_trend_regime_block" in decision.reasons
    assert decision.reason == "statarb_mr_trend_regime_block"


def test_statarb_mr_in_range_is_not_blocked_by_trend_rule():
    decision = _decision(
        regime_decision=_range_regime(),
        strategy_decision=_statarb_mr_strategy(),
    )
    assert decision.passed


def test_statarb_mr_in_risk_off_is_not_blocked_by_trend_rule():
    regime = SimpleNamespace(regime="RISK_OFF", reason_codes=[])
    decision = _decision(
        config=_config(block_risk_off_thin_liquidity=False, block_risk_off_vol_shock=False),
        regime_decision=regime,
        strategy_decision=_statarb_mr_strategy(),
    )
    assert decision.passed
    assert "statarb_mr_trend_regime_block" not in decision.reasons


def test_non_mr_strategy_in_trend_is_not_blocked_by_trend_rule():
    decision = _decision(
        regime_decision=_trend_regime(),
        strategy_decision=_other_strategy("DEFENSIVE"),
    )
    assert decision.passed
    assert "statarb_mr_trend_regime_block" not in decision.reasons


def test_statarb_mr_trend_block_respects_config_flag_false():
    decision = _decision(
        config=_config(block_statarb_mr_in_trend=False),
        regime_decision=_trend_regime(),
        strategy_decision=_statarb_mr_strategy(),
    )
    assert decision.passed
    assert "statarb_mr_trend_regime_block" not in decision.reasons


def test_statarb_mr_trend_block_metadata_fields():
    decision = _decision(
        regime_decision=_trend_regime(),
        strategy_decision=_statarb_mr_strategy(),
    )
    payload = decision.to_payload()
    assert payload.get("statarb_mr_trend_blocked") is True
    assert payload.get("blocked_regime") == "TREND"


def test_statarb_mr_trend_block_no_metadata_when_not_blocked():
    decision = _decision(
        regime_decision=_range_regime(),
        strategy_decision=_statarb_mr_strategy(),
    )
    payload = decision.to_payload()
    assert "statarb_mr_trend_blocked" not in payload
    assert "blocked_regime" not in payload


def test_statarb_mr_trend_block_config_in_thresholds_payload():
    decision = _decision(
        regime_decision=_trend_regime(),
        strategy_decision=_statarb_mr_strategy(),
    )
    payload = decision.to_payload()
    thresholds = payload.get("config_thresholds", {})
    assert "block_statarb_mr_in_trend" in thresholds
    assert thresholds["block_statarb_mr_in_trend"] is True


def test_statarb_mr_trend_block_does_not_affect_other_gate_checks():
    # Cointegration failure should still fire independently of the TREND block
    decision = _decision(
        config=_config(block_statarb_mr_in_trend=False),
        regime_decision=_trend_regime(),
        strategy_decision=_statarb_mr_strategy(),
        quality_decision=_quality(cointegration=5.0),
    )
    assert not decision.passed
    assert "cointegration_component_below_threshold" in decision.reasons
    assert "statarb_mr_trend_regime_block" not in decision.reasons


def test_statarb_mr_trend_block_disabled_gate_not_blocked():
    decision = _decision(
        config=_config(enabled=False),
        regime_decision=_trend_regime(),
        strategy_decision=_statarb_mr_strategy(),
    )
    assert decision.passed
    assert decision.reason == "entry_safety_gate_disabled"


def test_statarb_mr_trend_block_fires_when_shadow_router_shows_trend_spread():
    # Shadow router commits to TREND_SPREAD via hysteresis, but execution strategy is still STATARB_MR.
    # entry_strategy_name overrides the router's active_strategy for the block check.
    decision = _decision(
        regime_decision=_trend_regime(),
        strategy_decision=_other_strategy("TREND_SPREAD"),
        entry_strategy_name="STATARB_MR",
    )
    assert not decision.passed
    assert "statarb_mr_trend_regime_block" in decision.reasons


def test_statarb_mr_trend_block_blind_spot_without_entry_strategy_name():
    # Without entry_strategy_name, gate falls back to router's active_strategy ("TREND_SPREAD").
    # The block does not fire — documents the pre-fix failure mode for regression tracking.
    decision = _decision(
        regime_decision=_trend_regime(),
        strategy_decision=_other_strategy("TREND_SPREAD"),
    )
    assert decision.passed
    assert "statarb_mr_trend_regime_block" not in decision.reasons


# --- Patch 7: Forward-looking cointegration stability entry filter ---


def test_coint_stability_blocks_rising_pvalue():
    cfg = _config(
        coint_stability_enabled=True,
        coint_stability_window=3,
        coint_stability_slope_max=0.010,
        coint_stability_min_sample_interval_seconds=60.0,
    )
    _decision(config=cfg, now=1000.0, metrics={**_good_metrics(), "p_value": 0.020})
    _decision(config=cfg, now=1060.0, metrics={**_good_metrics(), "p_value": 0.040})
    decision = _decision(config=cfg, now=1120.0, metrics={**_good_metrics(), "p_value": 0.060})
    assert "coint_stability_slope_high" in decision.reasons
    assert decision.component_scores["coint_stability_check_evaluated_count"] == 1.0
    assert decision.component_scores["coint_stability_check_blocked_count"] == 1.0


def test_coint_stability_allows_stable_pvalue():
    cfg = _config(
        coint_stability_enabled=True,
        coint_stability_window=3,
        coint_stability_slope_max=0.010,
        coint_stability_min_sample_interval_seconds=60.0,
    )
    _decision(config=cfg, now=1000.0, metrics={**_good_metrics(), "p_value": 0.020})
    _decision(config=cfg, now=1060.0, metrics={**_good_metrics(), "p_value": 0.020})
    decision = _decision(config=cfg, now=1120.0, metrics={**_good_metrics(), "p_value": 0.020})
    assert "coint_stability_slope_high" not in decision.reasons
    assert decision.component_scores["coint_stability_check_evaluated_count"] == 1.0
    assert decision.component_scores["coint_stability_check_blocked_count"] == 0.0


def test_coint_stability_allows_improving_pvalue():
    cfg = _config(
        coint_stability_enabled=True,
        coint_stability_window=3,
        coint_stability_slope_max=0.010,
        coint_stability_min_sample_interval_seconds=60.0,
    )
    _decision(config=cfg, now=1000.0, metrics={**_good_metrics(), "p_value": 0.060})
    _decision(config=cfg, now=1060.0, metrics={**_good_metrics(), "p_value": 0.040})
    decision = _decision(config=cfg, now=1120.0, metrics={**_good_metrics(), "p_value": 0.020})
    assert "coint_stability_slope_high" not in decision.reasons
    assert decision.component_scores["coint_stability_check_evaluated_count"] == 1.0
    assert decision.component_scores["coint_stability_check_blocked_count"] == 0.0


def test_coint_stability_insufficient_history_allows():
    cfg = _config(
        coint_stability_enabled=True,
        coint_stability_window=5,
        coint_stability_slope_max=0.010,
        coint_stability_min_sample_interval_seconds=60.0,
    )
    _decision(config=cfg, now=1000.0, metrics={**_good_metrics(), "p_value": 0.010})
    decision = _decision(config=cfg, now=1060.0, metrics={**_good_metrics(), "p_value": 0.090})
    assert "coint_stability_slope_high" not in decision.reasons
    assert decision.component_scores["coint_stability_insufficient_history_count"] == 1.0
    assert decision.component_scores["coint_stability_check_evaluated_count"] == 0.0


def test_coint_stability_disabled_skips_check():
    cfg = _config(coint_stability_enabled=False)
    _decision(config=cfg, now=1000.0, metrics={**_good_metrics(), "p_value": 0.010})
    _decision(config=cfg, now=1060.0, metrics={**_good_metrics(), "p_value": 0.050})
    decision = _decision(config=cfg, now=1120.0, metrics={**_good_metrics(), "p_value": 0.090})
    assert "coint_stability_slope_high" not in decision.reasons
    assert "coint_stability_check_evaluated_count" not in decision.component_scores
    assert "coint_stability_check_blocked_count" not in decision.component_scores


def test_coint_stability_sample_interval_enforced():
    # Verifies that samples closer than MIN_SAMPLE_INTERVAL_SECONDS are not appended.
    # Without enforcement: the t=30 call would add p=0.090, giving 2 samples → block.
    # With enforcement: t=30 sample is skipped; buffer still has 1 entry → insufficient → allow.
    cfg = _config(
        coint_stability_enabled=True,
        coint_stability_window=2,
        coint_stability_slope_max=0.010,
        coint_stability_min_sample_interval_seconds=60.0,
    )
    _decision(config=cfg, now=0.0, metrics={**_good_metrics(), "p_value": 0.010})
    decision_too_soon = _decision(config=cfg, now=30.0, metrics={**_good_metrics(), "p_value": 0.090})
    assert "coint_stability_slope_high" not in decision_too_soon.reasons
    assert decision_too_soon.component_scores["coint_stability_insufficient_history_count"] == 1.0
    # 60s from first sample — appended; 2-point slope = 0.080 > 0.010 → block
    decision_ok = _decision(config=cfg, now=60.0, metrics={**_good_metrics(), "p_value": 0.090})
    assert "coint_stability_slope_high" in decision_ok.reasons


# --- Patch 7.1: record_entry_coint_pvalue pre-populates the ring buffer ---


def test_record_entry_coint_pvalue_enables_gate_evaluation():
    # Pre-populate the buffer via the monitoring-loop path (5 samples at 60s intervals).
    # The gate should see evaluated_count=1, not insufficient_history, on the first gate call.
    # Uses the _decision helper's default pair so buffer key alignment is guaranteed.
    cfg = _config(
        coint_stability_enabled=True,
        coint_stability_window=5,
        coint_stability_slope_max=0.020,
        coint_stability_min_sample_interval_seconds=60.0,
    )
    pair = "AAA-USDT-SWAP/BBB-USDT-SWAP"
    for i in range(5):
        record_entry_coint_pvalue(pair, 0.05 + i * 0.001, float(i * 60), config=cfg)
    # First gate call — buffer is full, slope should be computable
    decision = _decision(config=cfg, now=300.0, metrics={**_good_metrics(), "p_value": 0.054})
    assert decision.component_scores["coint_stability_check_evaluated_count"] == 1.0
    assert decision.component_scores["coint_stability_insufficient_history_count"] == 0.0


def test_record_entry_coint_pvalue_respects_sample_interval():
    # The monitoring loop runs every few seconds. Verify that rapid successive calls
    # to record_entry_coint_pvalue only append one sample per min_sample_interval window,
    # matching the interval gate inside the entry safety gate itself.
    cfg = _config(
        coint_stability_enabled=True,
        coint_stability_window=2,
        coint_stability_slope_max=0.010,
        coint_stability_min_sample_interval_seconds=60.0,
    )
    pair = "AAA-USDT-SWAP/BBB-USDT-SWAP"
    record_entry_coint_pvalue(pair, 0.010, 0.0, config=cfg)
    # Rapid follow-up calls within the 60s window — must not append
    record_entry_coint_pvalue(pair, 0.090, 10.0, config=cfg)
    record_entry_coint_pvalue(pair, 0.090, 20.0, config=cfg)
    record_entry_coint_pvalue(pair, 0.090, 30.0, config=cfg)
    # Gate call at t=31 — buffer has 1 sample, should be insufficient_history (not blocked)
    decision = _decision(config=cfg, now=31.0, metrics={**_good_metrics(), "p_value": 0.090})
    assert "coint_stability_slope_high" not in decision.reasons
    assert decision.component_scores["coint_stability_insufficient_history_count"] == 1.0


# --- Patch 7 telemetry: entry slope persistence for accepted trades ---

import func_pair_state as _fps  # noqa: E402


def _with_tmp_pair_state(fn):
    """Run fn with func_pair_state redirected to a temp file."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        orig_state_dir = _fps._STATE_DIR
        orig_state_file = _fps.STATE_FILE
        orig_lock_file = _fps._STATE_LOCK_FILE
        _fps._STATE_DIR = tmp_path
        _fps.STATE_FILE = tmp_path / "pair_strategy_state.json"
        _fps._STATE_LOCK_FILE = tmp_path / "pair_strategy_state.json.lock"
        try:
            fn()
        finally:
            _fps._STATE_DIR = orig_state_dir
            _fps.STATE_FILE = orig_state_file
            _fps._STATE_LOCK_FILE = orig_lock_file


def test_entry_gate_components_persisted_and_retrieved():
    # set_entry_trade_context stores entry_gate_components; get_entry_gate_components retrieves slope.
    def _run():
        from func_pair_state import set_entry_trade_context, get_entry_gate_components
        gate_components = {
            "coint_stability_slope": -0.00449,
            "coint_stability_check_evaluated_count": 1.0,
            "coint_stability_check_blocked_count": 0.0,
            "coint_stability_insufficient_history_count": 0.0,
        }
        set_entry_trade_context("STATARB_MR", "RANGE", entry_gate_components=gate_components)
        retrieved = get_entry_gate_components()
        assert retrieved.get("coint_stability_slope") == -0.00449
        assert retrieved.get("coint_stability_check_evaluated_count") == 1.0

    _with_tmp_pair_state(_run)


def test_entry_gate_components_absent_returns_empty_dict():
    # get_entry_gate_components returns {} when no components were persisted (e.g., pre-patch trade).
    def _run():
        from func_pair_state import get_entry_gate_components
        result = get_entry_gate_components()
        assert result == {}
        assert result.get("coint_stability_slope") is None

    _with_tmp_pair_state(_run)
