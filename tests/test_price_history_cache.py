from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRATEGY_ROOT = ROOT / "Strategy"
if str(STRATEGY_ROOT) not in sys.path:
    sys.path.insert(0, str(STRATEGY_ROOT))

import func_prices_json as fp


class _DummyLogger:
    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None


def _kline(ts: int, close: float) -> dict:
    return {
        "timestamp": str(ts),
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1.0,
        "volume_ccy": 1.0,
    }


def _okx_row(ts: int, close: float) -> list[str]:
    value = str(close)
    return [str(ts), value, value, value, value, "1", "1"]


def test_store_price_history_backfills_when_cache_is_shorter_than_target(monkeypatch, tmp_path):
    symbol = "BTC-USDT-SWAP"
    strategy_file = tmp_path / "Strategy" / "func_prices_json.py"
    output_dir = strategy_file.parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "1_price_list.json"
    output_path.write_text(
        json.dumps(
            {
                symbol: {
                    "symbol_info": {"symbol": symbol},
                    "klines": [_kline(1000, 100.0)],
                }
            }
        ),
        encoding="utf-8",
    )

    latest_calls = []
    history_calls = []

    def fake_latest_klines(inst_id: str, limit: int):
        latest_calls.append((inst_id, limit))
        return {"code": "0", "data": [_okx_row(2000, 101.0)]}

    def fake_price_klines(inst_id: str):
        history_calls.append(inst_id)
        return {
            "code": "0",
            "data": [
                _okx_row(3000, 102.0),
                _okx_row(2000, 101.0),
                _okx_row(1000, 100.0),
            ],
        }

    monkeypatch.setattr(fp, "__file__", str(strategy_file))
    monkeypatch.setattr(fp, "get_strategy_logger", lambda: _DummyLogger())
    monkeypatch.setattr(fp, "get_latest_klines", fake_latest_klines)
    monkeypatch.setattr(fp, "get_price_klines", fake_price_klines)
    monkeypatch.setattr(fp, "kline_limit", 3)
    monkeypatch.setattr(fp, "time_frame", "1m")
    monkeypatch.setenv("STATBOT_STRATEGY_INTERNAL_KLINE_WORKERS", "1")
    monkeypatch.setenv("STATBOT_STRATEGY_INTERNAL_CACHE_SLEEP", "0")
    monkeypatch.setenv("STATBOT_STRATEGY_INTERNAL_KLINE_SLEEP", "0")

    fp.store_price_history([{"symbol": symbol}])

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert latest_calls == []
    assert history_calls == [symbol]
    assert len(saved[symbol]["klines"]) == 3
    assert saved[symbol]["symbol_info"]["total_klines"] == 3
