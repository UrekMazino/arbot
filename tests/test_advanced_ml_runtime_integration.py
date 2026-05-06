from __future__ import annotations

from Execution.advanced_ml_runtime import (
    advanced_ml_runtime_mode,
    evaluate_probabilistic_exit,
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
