import os
import sys
import tempfile
import types
from pathlib import Path


def _install_okx_stub():
    okx_mod = types.ModuleType("okx")
    public_mod = types.ModuleType("okx.PublicData")
    account_mod = types.ModuleType("okx.Account")
    trade_mod = types.ModuleType("okx.Trade")
    market_mod = types.ModuleType("okx.MarketData")

    class _StubAPI:
        def __init__(self, *args, **kwargs):
            pass

        def __getattr__(self, _name):
            def _noop(*_args, **_kwargs):
                return {"code": "0", "data": []}

            return _noop

    public_mod.PublicAPI = _StubAPI
    account_mod.AccountAPI = _StubAPI
    trade_mod.TradeAPI = _StubAPI
    market_mod.MarketAPI = _StubAPI

    okx_mod.PublicData = public_mod
    okx_mod.Account = account_mod
    okx_mod.Trade = trade_mod
    okx_mod.MarketData = market_mod

    sys.modules["okx"] = okx_mod
    sys.modules["okx.PublicData"] = public_mod
    sys.modules["okx.Account"] = account_mod
    sys.modules["okx.Trade"] = trade_mod
    sys.modules["okx.MarketData"] = market_mod


os.environ["STATBOT_SKIP_INSTRUMENT_FETCH"] = "1"
os.environ["STATBOT_LOG_PATH"] = os.path.join(tempfile.gettempdir(), "okxstatbot-test-adaptive-entry.log")
_install_okx_stub()

ROOT_DIR = Path(__file__).resolve().parents[1]
EXEC_DIR = ROOT_DIR / "Execution"
if str(EXEC_DIR) not in sys.path:
    sys.path.append(str(EXEC_DIR))

import func_trade_management as ftm


def _run_signal(monkeypatch, persistence_history):
    monkeypatch.setattr(ftm, "ENTRY_MIN_QUALIFIED_BARS", 0)
    monkeypatch.setattr(ftm, "ENTRY_Z_TOLERANCE", 0.05)
    monkeypatch.setattr(ftm, "ENTRY_EXTREME_CLEAN_BARS", 2)

    import func_pair_state

    monkeypatch.setattr(func_pair_state, "can_reenter", lambda cooldown_minutes=5: True)
    monkeypatch.setattr(func_pair_state, "add_to_persistence_history", lambda _z: None)
    monkeypatch.setattr(func_pair_state, "get_persistence_history", lambda: list(persistence_history))

    return ftm.generate_signal(
        [persistence_history[-1]],
        cointegration_ok=1,
        in_position=False,
        entry_z=2.0,
        entry_z_max=3.0,
        min_persist_bars=4,
    )


def _run_timestamped_signal(monkeypatch, persistence_history, min_continuous_seconds=60):
    monkeypatch.setattr(ftm, "ENTRY_MIN_QUALIFIED_BARS", 0)
    monkeypatch.setattr(ftm, "ENTRY_Z_TOLERANCE", 0.05)
    monkeypatch.setattr(ftm, "ENTRY_EXTREME_CLEAN_BARS", 2)
    monkeypatch.setattr(ftm, "ENTRY_MIN_CONTINUOUS_SECONDS", min_continuous_seconds)

    import func_pair_state

    monkeypatch.setattr(func_pair_state, "can_reenter", lambda cooldown_minutes=5: True)
    monkeypatch.setattr(func_pair_state, "add_to_persistence_history", lambda _z: None)
    monkeypatch.setattr(func_pair_state, "get_persistence_history", lambda: list(persistence_history))

    return ftm.generate_signal(
        [persistence_history[-1]["z"]],
        cointegration_ok=1,
        in_position=False,
        entry_z=2.0,
        entry_z_max=3.0,
        min_persist_bars=4,
    )


def test_adaptive_persistence_accepts_three_of_four_with_tolerance(monkeypatch):
    signal, reason = _run_signal(monkeypatch, [-1.84, -1.98, -2.10, -2.33])

    assert signal == "BUY_SPREAD"
    assert "adaptive persistence" in reason
    assert "qualified=3/4" in reason
    assert "tolerance=0.05" in reason


def test_adaptive_persistence_rejects_when_qualified_count_is_too_low(monkeypatch):
    signal, reason = _run_signal(monkeypatch, [-1.65, -1.84, -1.98, -2.10])

    assert signal is None
    assert "adaptive persistence not satisfied" in reason
    assert "qualified=2/4" in reason


def test_adaptive_persistence_reports_below_threshold_separately(monkeypatch):
    signal, reason = _run_signal(monkeypatch, [0.71, 0.78, 0.89, 0.98])

    assert signal is None
    assert "below entry threshold" in reason
    assert "need=+/-1.95" in reason


def test_adaptive_persistence_waits_for_clean_bars_after_extreme(monkeypatch):
    signal, reason = _run_signal(monkeypatch, [3.68, 3.68, 2.62, 2.66])

    assert signal is None
    assert "adaptive persistence not satisfied" in reason
    assert "qualified=2/4" in reason


def test_adaptive_persistence_allows_return_from_extreme_after_clean_cluster(monkeypatch):
    signal, reason = _run_signal(monkeypatch, [3.68, 2.62, 2.66, 2.73])

    assert signal == "SELL_SPREAD"
    assert "adaptive persistence" in reason
    assert "qualified=3/4" in reason


def test_adaptive_persistence_still_blocks_current_too_extreme(monkeypatch):
    signal, reason = _run_signal(monkeypatch, [2.62, 2.66, 2.73, 3.20])

    assert signal is None
    assert "too extreme for short entry" in reason


def test_continuous_interval_blocks_fresh_entry_cluster(monkeypatch):
    signal, reason = _run_timestamped_signal(
        monkeypatch,
        [
            {"ts": 100.0, "z": -2.08},
            {"ts": 115.0, "z": -2.12},
            {"ts": 130.0, "z": -2.20},
            {"ts": 145.0, "z": -2.31},
        ],
        min_continuous_seconds=60,
    )

    assert signal is None
    assert "continuous interval not satisfied" in reason
    assert "continuous=45s" in reason


def test_continuous_interval_allows_mature_entry_cluster(monkeypatch):
    signal, reason = _run_timestamped_signal(
        monkeypatch,
        [
            {"ts": 100.0, "z": -2.08},
            {"ts": 125.0, "z": -2.12},
            {"ts": 150.0, "z": -2.20},
            {"ts": 175.0, "z": -2.31},
        ],
        min_continuous_seconds=60,
    )

    assert signal == "BUY_SPREAD"
    assert "adaptive persistence" in reason
