import sys
from pathlib import Path

import numpy as np

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import func_get_zscore as fgz
import func_pair_state


def _coint_metrics(*, coint_flag, p_value, adf_stat, latest_zscore):
    return {
        "coint_flag": coint_flag,
        "p_value": p_value,
        "adf_stat": adf_stat,
        "critical_value": -3.4,
        "zero_crossings": 12,
        "spread_trend": 0.0,
        "correlation": 0.82,
        "returns_correlation": 0.55,
        "hedge_ratio": 1.1,
        "latest_zscore": latest_zscore,
        "zscore_values": np.array([0.0, latest_zscore], dtype=float),
    }


def test_orderbook_entry_z_uses_stable_kline_only_cointegration(monkeypatch):
    monkeypatch.setenv("STATBOT_LIVE_COINT_USE_KLINE_ONLY", "1")
    monkeypatch.setenv("STATBOT_LIVE_COINT_LIMIT", "80")
    monkeypatch.setenv("STATBOT_LIVE_COINT_WINDOW", "20")
    monkeypatch.setattr(func_pair_state, "reset_price_fetch_failures", lambda: None)

    fetch_calls = []
    eval_calls = []

    def fake_get_latest_klines(**kwargs):
        fetch_calls.append(kwargs)
        return list(range(1, 81)), list(range(101, 181))

    def fake_fetch_mid_price(inst_id, **_kwargs):
        return 999.0 if inst_id == "AAA-USDT-SWAP" else 888.0

    def fake_evaluate_cointegration(series_1, series_2, *, window, **_kwargs):
        eval_calls.append((float(series_1[-1]), float(series_2[-1]), int(window), len(series_1)))
        if float(series_1[-1]) == 999.0:
            return _coint_metrics(coint_flag=0, p_value=0.40, adf_stat=-3.0, latest_zscore=2.25)
        return _coint_metrics(coint_flag=1, p_value=0.01, adf_stat=-4.2, latest_zscore=1.10)

    monkeypatch.setattr(fgz, "get_latest_klines", fake_get_latest_klines)
    monkeypatch.setattr(fgz, "_fetch_mid_price", fake_fetch_mid_price)
    monkeypatch.setattr(fgz, "evaluate_cointegration", fake_evaluate_cointegration)

    zscores, sign_positive, metrics = fgz.get_latest_zscore(
        inst_id_1="AAA-USDT-SWAP",
        inst_id_2="BBB-USDT-SWAP",
        limit=80,
        window=5,
        use_orderbook=True,
    )

    assert fetch_calls and len(fetch_calls) == 1
    assert eval_calls == [(999.0, 888.0, 5, 80), (80.0, 180.0, 20, 80)]
    assert zscores == [0.0, 2.25]
    assert sign_positive is True
    assert metrics["price_1"] == 999.0
    assert metrics["price_2"] == 888.0
    assert metrics["entry_basis"] == "orderbook_mid"
    assert metrics["entry_coint_flag"] == 0
    assert metrics["entry_coint_health"] == "broken"
    assert metrics["coint_basis"] == "kline_only"
    assert metrics["coint_window"] == 20
    assert metrics["coint_sample_size"] == 80
    assert metrics["coint_flag"] == 1
    assert metrics["coint_health"] == "valid"
    assert metrics["p_value"] == 0.01


def test_kline_only_precheck_does_not_run_extra_stable_fetch(monkeypatch):
    monkeypatch.setenv("STATBOT_LIVE_COINT_USE_KLINE_ONLY", "1")
    monkeypatch.setenv("STATBOT_LIVE_COINT_LIMIT", "80")
    monkeypatch.setenv("STATBOT_LIVE_COINT_WINDOW", "20")

    fetch_calls = []
    eval_calls = []

    def fake_get_latest_klines(**kwargs):
        fetch_calls.append(kwargs)
        return list(range(1, 81)), list(range(101, 181))

    def fake_evaluate_cointegration(series_1, series_2, *, window, **_kwargs):
        eval_calls.append((float(series_1[-1]), float(series_2[-1]), int(window), len(series_1)))
        return _coint_metrics(coint_flag=1, p_value=0.01, adf_stat=-4.2, latest_zscore=1.10)

    monkeypatch.setattr(fgz, "get_latest_klines", fake_get_latest_klines)
    monkeypatch.setattr(fgz, "evaluate_cointegration", fake_evaluate_cointegration)

    _zscores, _sign_positive, metrics = fgz.get_latest_zscore(
        inst_id_1="AAA-USDT-SWAP",
        inst_id_2="BBB-USDT-SWAP",
        limit=80,
        window=20,
        use_orderbook=False,
    )

    assert len(fetch_calls) == 1
    assert eval_calls == [(80.0, 180.0, 20, 80)]
    assert metrics["entry_basis"] == "kline"
    assert metrics["coint_basis"] == "kline_only"
    assert metrics["entry_coint_flag"] == metrics["coint_flag"] == 1
