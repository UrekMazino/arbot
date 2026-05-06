import sys
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
EXECUTION_DIR = ROOT_DIR / "Execution"
if str(EXECUTION_DIR) not in sys.path:
    sys.path.insert(0, str(EXECUTION_DIR))

from func_event_emitter import EventEmitter
from func_event_emitter import _KNOWN_EVENT_TYPES


def test_emit_flush_forces_small_batch(monkeypatch, tmp_path):
    monkeypatch.setenv("STATBOT_EVENT_EMITTER_MODE", "active")
    monkeypatch.setenv("STATBOT_EVENT_BATCH_SIZE", "25")
    monkeypatch.setenv("STATBOT_EVENT_FLUSH_SECONDS", "9999")
    monkeypatch.setenv("STATBOT_EVENT_SPOOL_DIR", str(tmp_path))
    monkeypatch.setenv("STATBOT_EVENT_API_BASE", "http://example.test/api/v2")
    monkeypatch.setenv("STATBOT_BOT_INSTANCE_ID", "bot-test")
    monkeypatch.setenv("STATBOT_RUN_ID", "run-test")

    emitter = EventEmitter()
    emitter._last_flush_ts = time.time()
    posted_batches = []

    def fake_post_batch(batch):
        posted_batches.append(list(batch))
        return True

    emitter._post_batch = fake_post_batch

    assert emitter.emit("trade_close", payload={"pnl_usdt": -2.5}, flush=True)

    assert len(posted_batches) == 1
    assert posted_batches[0][0]["event_type"] == "trade_close"
    assert posted_batches[0][0]["payload"]["pnl_usdt"] == -2.5
    assert emitter._queue == []


def test_emit_without_flush_respects_interval(monkeypatch, tmp_path):
    monkeypatch.setenv("STATBOT_EVENT_EMITTER_MODE", "active")
    monkeypatch.setenv("STATBOT_EVENT_BATCH_SIZE", "25")
    monkeypatch.setenv("STATBOT_EVENT_FLUSH_SECONDS", "9999")
    monkeypatch.setenv("STATBOT_EVENT_SPOOL_DIR", str(tmp_path))
    monkeypatch.setenv("STATBOT_EVENT_API_BASE", "http://example.test/api/v2")
    monkeypatch.setenv("STATBOT_BOT_INSTANCE_ID", "bot-test")
    monkeypatch.setenv("STATBOT_RUN_ID", "run-test")

    emitter = EventEmitter()
    emitter._last_flush_ts = time.time()
    posted_batches = []
    emitter._post_batch = lambda batch: posted_batches.append(list(batch)) or True

    assert emitter.emit("heartbeat", payload={"equity_usdt": 1000.0}, flush=False)

    assert posted_batches == []
    assert len(emitter._queue) == 1


def test_advanced_ml_regime_shadow_is_registered_event_type():
    assert "advanced_ml_regime_shadow" in _KNOWN_EVENT_TYPES
    assert "advanced_ml_regime_live" in _KNOWN_EVENT_TYPES
