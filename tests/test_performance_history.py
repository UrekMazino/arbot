from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Platform.api.app.database import Base
from Platform.api.app.models import BotInstance, Run, Trade
from Platform.api.app.routers import runs


def _build_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(bind=engine, autocommit=False, autoflush=False)


def test_performance_history_groups_closed_trades_by_strategy_and_regime():
    engine, session_factory = _build_session_factory()
    db = session_factory()
    try:
        bot = BotInstance(id="bot-performance-1", name="default", environment="demo", is_active=True)
        start_ts = datetime(2026, 4, 22, 1, 0, 0, tzinfo=timezone.utc)
        run_a = Run(
            id="run-perf-a",
            bot_instance_id=bot.id,
            run_key="run_perf_a",
            status="stopped",
            start_ts=start_ts,
            start_equity=1000.0,
        )
        run_b = Run(
            id="run-perf-b",
            bot_instance_id=bot.id,
            run_key="run_perf_b",
            status="stopped",
            start_ts=start_ts + timedelta(hours=1),
            start_equity=1001.0,
        )
        db.add_all([bot, run_a, run_b])
        db.flush()

        trades = [
            Trade(
                id="trade-mr-win",
                run_id=run_a.id,
                pair_key="ETH-USDT-SWAP/SOL-USDT-SWAP",
                entry_ts=start_ts,
                exit_ts=start_ts + timedelta(minutes=8),
                pnl_usdt=2.5,
                hold_minutes=8,
                entry_strategy="STATARB_MR",
                entry_regime="RANGE",
                size_multiplier_used=1.0,
            ),
            Trade(
                id="trade-mr-loss",
                run_id=run_a.id,
                pair_key="BTC-USDT-SWAP/ETH-USDT-SWAP",
                entry_ts=start_ts + timedelta(minutes=10),
                exit_ts=start_ts + timedelta(minutes=18),
                pnl_usdt=-1.0,
                hold_minutes=8,
                entry_strategy="STATARB_MR",
                entry_regime="RANGE",
                size_multiplier_used=1.0,
            ),
            Trade(
                id="trade-trend-win",
                run_id=run_b.id,
                pair_key="FIL-USDT-SWAP/QTUM-USDT-SWAP",
                entry_ts=start_ts + timedelta(hours=1),
                exit_ts=start_ts + timedelta(hours=1, minutes=20),
                pnl_usdt=1.2,
                hold_minutes=20,
                entry_strategy="TREND_SPREAD",
                entry_regime="TREND",
                size_multiplier_used=0.35,
            ),
        ]
        db.add_all(trades)
        db.commit()

        response = runs.performance_history(range_key="all", limit=100, _=object(), db=db)

        assert response["closed_trades"] == 3
        assert response["closed_trades_with_pnl"] == 3
        assert response["run_count"] == 2
        assert response["total_pnl_usdt"] == 2.7

        by_strategy = {row["strategy"]: row for row in response["strategy_summary"]}
        assert by_strategy["STATARB_MR"]["trades"] == 2
        assert by_strategy["STATARB_MR"]["wins"] == 1
        assert by_strategy["STATARB_MR"]["losses"] == 1
        assert by_strategy["STATARB_MR"]["win_rate_pct"] == 50.0
        assert by_strategy["STATARB_MR"]["pnl_usdt"] == 1.5
        assert by_strategy["TREND_SPREAD"]["trades"] == 1
        assert by_strategy["TREND_SPREAD"]["avg_size_multiplier"] == 0.35

        by_strategy_regime = {
            (row["strategy"], row["regime"]): row
            for row in response["strategy_regime_summary"]
        }
        assert by_strategy_regime[("STATARB_MR", "RANGE")]["trades"] == 2
        assert by_strategy_regime[("TREND_SPREAD", "TREND")]["pnl_usdt"] == 1.2
        assert response["recent_trades"][0]["id"] == "trade-trend-win"
        assert response["recent_trades"][0]["cumulative_pnl_usdt"] == 2.7
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
