from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRATEGY_ROOT = ROOT / "Strategy"
if str(STRATEGY_ROOT) not in sys.path:
    sys.path.insert(0, str(STRATEGY_ROOT))

import func_price_klines as klines


class _DummyLogger:
    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def exception(self, *args, **kwargs):
        return None


class _NoRateLimit:
    def acquire(self):
        return None


class _MarketSession:
    def __init__(self):
        self.recent_after_values: list[str] = []
        self.history_after_values: list[str] = []

    def get_candlesticks(self, *, instId, after="", before="", bar="", limit=""):
        self.recent_after_values.append(str(after or ""))
        if not after:
            return {"code": "0", "data": [_row(300), _row(200)]}
        if str(after) == "200":
            return {"code": "0", "data": []}
        raise AssertionError(f"unexpected recent after={after}")

    def get_history_candlesticks(self, *, instId, after="", before="", bar="", limit=""):
        self.history_after_values.append(str(after or ""))
        if str(after) == "200":
            return {"code": "0", "data": [_row(100)]}
        raise AssertionError(f"unexpected history after={after}")


class _RateLimitedRecentSession:
    def __init__(self):
        self.calls = 0

    def get_candlesticks(self, *, instId, after="", before="", bar="", limit=""):
        self.calls += 1
        if self.calls == 1:
            return {"code": "50011", "msg": "Too Many Requests", "data": []}
        return {"code": "0", "data": [_row(300)]}

    def get_history_candlesticks(self, *, instId, after="", before="", bar="", limit=""):
        raise AssertionError("history endpoint should not be needed")


def _row(ts: int) -> list[str]:
    value = str(float(ts))
    return [str(ts), value, value, value, value, "1", "1"]


def test_get_price_klines_continues_with_history_endpoint(monkeypatch):
    session = _MarketSession()
    monkeypatch.setattr(klines, "market_session", session)
    monkeypatch.setattr(klines, "_KLINE_RATE_LIMITER", _NoRateLimit())
    monkeypatch.setattr(klines, "get_strategy_logger", lambda: _DummyLogger())
    monkeypatch.setattr(klines, "kline_limit", 3)
    monkeypatch.setattr(klines, "time_frame", "1m")
    monkeypatch.setattr(klines.time, "sleep", lambda _seconds: None)

    result = klines.get_price_klines("BTC-USDT-SWAP")

    assert result["code"] == "0"
    assert [row[0] for row in result["data"]] == ["300", "200", "100"]
    assert session.recent_after_values == [""]
    assert session.history_after_values == ["200"]


def test_get_price_klines_retries_rate_limited_response(monkeypatch):
    session = _RateLimitedRecentSession()
    sleeps: list[float] = []
    monkeypatch.setattr(klines, "market_session", session)
    monkeypatch.setattr(klines, "_KLINE_RATE_LIMITER", _NoRateLimit())
    monkeypatch.setattr(klines, "get_strategy_logger", lambda: _DummyLogger())
    monkeypatch.setattr(klines, "kline_limit", 1)
    monkeypatch.setattr(klines, "time_frame", "1m")
    monkeypatch.setattr(klines, "_KLINE_RATE_LIMIT_RETRIES", 3)
    monkeypatch.setattr(klines, "_KLINE_RATE_LIMIT_BASE_DELAY", 1.25)
    monkeypatch.setattr(klines, "_KLINE_RATE_LIMIT_MAX_DELAY", 5.0)
    monkeypatch.setattr(klines.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = klines.get_price_klines("BTC-USDT-SWAP")

    assert result["code"] == "0"
    assert [row[0] for row in result["data"]] == ["300"]
    assert session.calls == 2
    assert sleeps[0] == 1.25
