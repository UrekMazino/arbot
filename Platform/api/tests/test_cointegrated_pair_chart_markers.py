from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from app.models import BotInstance, Run, RunEvent, Trade
from app.services import cointegrated_pairs as cp


def _ts(minute: int) -> datetime:
    return datetime(2026, 5, 7, 2, minute, tzinfo=timezone.utc)


def _write_price_json(path: Path) -> None:
    rows_a = []
    rows_b = []
    for idx in range(8):
        ts_ms = int((_ts(0) + timedelta(minutes=idx)).timestamp() * 1000)
        rows_a.append({"timestamp": str(ts_ms), "close": 10.0 + idx * 0.2})
        rows_b.append({"timestamp": str(ts_ms), "close": 20.0 + idx * 0.1})
    path.write_text(
        json.dumps(
            {
                "AAA-USDT-SWAP": {"klines": rows_a},
                "BBB-USDT-SWAP": {"klines": rows_b},
            }
        ),
        encoding="utf-8",
    )


def test_pair_detail_adds_blocked_and_actual_trade_markers(monkeypatch, tmp_path, db_session):
    coint_csv = tmp_path / "2_cointegrated_pairs.csv"
    price_json = tmp_path / "1_price_list.json"
    status_json = tmp_path / "2_cointegrated_pairs_status.json"
    pd.DataFrame(
        [
            {
                "sym_1": "AAA-USDT-SWAP",
                "sym_2": "BBB-USDT-SWAP",
                "p_value": 0.001,
                "adf_stat": -4.5,
                "hedge_ratio": 0.8,
                "zero_crossing": 7,
            }
        ]
    ).to_csv(coint_csv, index=False)
    _write_price_json(price_json)
    status_json.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(cp, "COINT_CSV", coint_csv)
    monkeypatch.setattr(cp, "PRICE_JSON", price_json)
    monkeypatch.setattr(cp, "STATUS_JSON", status_json)
    monkeypatch.setattr(cp, "EXECUTION_ENV_FILE", tmp_path / "missing.env")
    monkeypatch.setenv("STATBOT_STRATEGY_Z_SCORE_WINDOW", "3")

    bot = BotInstance(id="bot-test", name="bot-test", environment="test")
    run = Run(
        id="run-test",
        bot_instance_id=bot.id,
        run_key="run_test",
        status="running",
        start_ts=_ts(0),
        start_equity=1000.0,
    )
    db_session.add_all([bot, run])
    db_session.flush()
    db_session.add(
        Trade(
            run_id=run.id,
            pair_key="AAA-USDT-SWAP/BBB-USDT-SWAP",
            entry_ts=_ts(1),
            exit_ts=_ts(4),
            side="long_positive_short_negative",
            entry_z=-2.1,
            exit_z=0.2,
            pnl_usdt=3.25,
        )
    )
    db_session.add(
        RunEvent(
            event_id="blocked-entry",
            run_id=run.id,
            bot_instance_id=bot.id,
            ts=_ts(3),
            event_type="entry_reject",
            severity="warn",
            payload_json={
                "reject_type": "trade_quality_gate",
                "reason": "score_below_threshold",
                "pair": "BBB-USDT-SWAP/AAA-USDT-SWAP",
                "score": 71.82,
                "min_score": 72.0,
                "diagnostics": {"latest_zscore": 1.96},
            },
        )
    )
    db_session.commit()

    detail = cp.get_cointegrated_pair_detail("AAA-USDT-SWAP", "BBB-USDT-SWAP", limit=50, db=db_session)

    stats = detail["stats"]["markers"]
    assert stats["actual_entries"] == 1
    assert stats["actual_exits"] == 1
    assert stats["blocked_entries"] == 1
    assert any(point["actual_entry_z"] == -2.1 for point in detail["points"])
    assert any(point["actual_exit_pnl_usdt"] == 3.25 for point in detail["points"])
    assert any("score 71.82/72.00" in str(point["blocked_entry_label"]) for point in detail["points"])
