from __future__ import annotations

from Execution.advanced_ml_runtime import (
    advanced_ml_runtime_mode,
    evaluate_probabilistic_exit,
    learn_from_closed_trade,
    reset_advanced_ml_runtime_cache,
    should_apply_live_advanced_exit,
)


def test_runtime_defaults_to_shadow_and_does_not_apply_live_exit(monkeypatch):
    monkeypatch.delenv("STATBOT_ADVANCED_ML_ENABLED", raising=False)
    monkeypatch.delenv("STATBOT_ADVANCED_ML_SHADOW_MODE", raising=False)
    reset_advanced_ml_runtime_cache()

    decision = evaluate_probabilistic_exit(
        pair=("AAA-USDT-SWAP", "BBB-USDT-SWAP"),
        zscore_series=[2.0, 1.9, 1.8],
        metrics={"coint_flag": 1},
        latest_zscore=1.8,
        entry_z=2.0,
        entry_time=1_800_000_000.0,
        entry_notional=100.0,
        floating_pnl_usdt=0.5,
        pnl_pct=0.5,
        old_action="hold",
        old_reason="legacy hold",
    )

    assert advanced_ml_runtime_mode() == "shadow"
    assert decision is not None
    assert decision.metadata["shadow_mode"] is True
    assert should_apply_live_advanced_exit(decision) is False


def test_runtime_live_mode_allows_explicit_advanced_exit(monkeypatch):
    monkeypatch.setenv("STATBOT_ADVANCED_ML_ENABLED", "1")
    monkeypatch.setenv("STATBOT_ADVANCED_ML_SHADOW_MODE", "0")
    monkeypatch.setenv("STATBOT_ADVANCED_ML_WARN_WHEN_USING_DEFAULT_SPREAD_EDGE", "0")
    reset_advanced_ml_runtime_cache()

    decision = evaluate_probabilistic_exit(
        pair=("AAA-USDT-SWAP", "BBB-USDT-SWAP"),
        zscore_series=[2.0, 3.0, 5.0],
        metrics={"coint_flag": 1},
        latest_zscore=5.0,
        entry_z=2.0,
        entry_time=1_800_000_000.0,
        entry_notional=100.0,
        floating_pnl_usdt=-2.0,
        pnl_pct=-2.0,
        old_action="hold",
        old_reason="legacy hold",
    )

    assert advanced_ml_runtime_mode() == "live"
    assert decision is not None
    assert decision.hard_kill_triggered is True
    assert should_apply_live_advanced_exit(decision) is True

    reset_advanced_ml_runtime_cache()


def test_live_soft_exit_is_blocked_without_phase6_shadow_evidence(monkeypatch):
    monkeypatch.setenv("STATBOT_ADVANCED_ML_ENABLED", "1")
    monkeypatch.setenv("STATBOT_ADVANCED_ML_SHADOW_MODE", "0")
    monkeypatch.setenv("STATBOT_ADVANCED_ML_ROLLOUT_REQUIRE_POSITIVE_SHADOW_REPORT", "1")
    monkeypatch.setenv("STATBOT_ADVANCED_ML_ROLLOUT_MIN_SHADOW_REPORTS", "10")
    monkeypatch.setenv("STATBOT_ADVANCED_ML_WARN_WHEN_USING_DEFAULT_SPREAD_EDGE", "0")
    reset_advanced_ml_runtime_cache()

    decision = evaluate_probabilistic_exit(
        pair=("AAA-USDT-SWAP", "BBB-USDT-SWAP"),
        zscore_series=[2.0, 2.2, 2.4, 2.6],
        metrics={"coint_flag": 0, "book_freshness_ms": 100, "pair_state": "stable"},
        latest_zscore=2.6,
        entry_z=2.0,
        entry_time=1_800_000_000.0,
        entry_notional=100.0,
        floating_pnl_usdt=-5.0,
        pnl_pct=-5.0,
        old_action="hold",
        old_reason="legacy hold",
    )

    assert decision is not None
    assert decision.hard_kill_triggered is False
    assert decision.metadata["rollout"]["allowed"] is False
    assert any(str(reason).startswith("shadow_reports=") for reason in decision.metadata["rollout"]["reasons"])
    assert should_apply_live_advanced_exit(decision) is False

    reset_advanced_ml_runtime_cache()


def test_closed_trade_learning_updates_and_flushes_models(monkeypatch, tmp_path):
    monkeypatch.setenv("STATBOT_ADVANCED_ML_ENABLED", "1")
    monkeypatch.setenv("STATBOT_ADVANCED_ML_SHADOW_MODE", "1")
    monkeypatch.setenv("STATBOT_ADVANCED_ML_MODEL_STATE_PATH", str(tmp_path))
    reset_advanced_ml_runtime_cache()

    result = learn_from_closed_trade(
        pair=("AAA-USDT-SWAP", "BBB-USDT-SWAP"),
        trade_id="AAA/BBB:1",
        actual_pnl_usdt=2.0,
        result_verified=True,
        history_recorded=True,
        entry_notional_usdt=200.0,
        fees_usdt=0.1,
        slippage_usdt=0.1,
        hold_seconds=120.0,
        metrics={
            "p_value": 0.01,
            "zero_crossing": 30,
            "correlation": 0.9,
            "hedge_ratio": 1.0,
            "adf_stat": -3.0,
            "pair_liquidity_min": 50_000,
            "pair_order_capacity_usdt": 500,
            "pair_state": "stable",
        },
    )

    assert result["skipped"] is False
    assert result["bayes_updated"] is True
    assert result["linucb_updated"] is True
    assert result["state_flushed"] is True
    assert (tmp_path / "bayesian_pair_scorer.json").exists()
    assert (tmp_path / "linucb.json").exists()

    reset_advanced_ml_runtime_cache()
