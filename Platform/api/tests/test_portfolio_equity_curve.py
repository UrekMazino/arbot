from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models import BotInstance, EquitySnapshot, Run, Trade
from app.routers.runs import _bucket_portfolio_points, _finish_portfolio_points
from app.routers.runs import portfolio_equity_curve


def _ts(hour: int, minute: int) -> datetime:
    return datetime(2026, 4, 30, hour, minute, tzinfo=timezone.utc)


def test_bucketed_portfolio_points_use_last_sample_timestamp() -> None:
    raw_points = [
        {"ts": _ts(10, 5), "equity": 100.0, "samples": 1, "run_key": "run_a"},
        {"ts": _ts(10, 55), "equity": 90.0, "samples": 1, "run_key": "run_a"},
        {"ts": _ts(11, 10), "equity": 95.0, "samples": 1, "run_key": "run_a"},
    ]

    bucketed = _bucket_portfolio_points(raw_points, "hour", 2000)

    assert len(bucketed) == 2
    assert bucketed[0]["ts"] == _ts(10, 55)
    assert bucketed[0]["_bucket_ts"] == _ts(10, 0)
    assert bucketed[0]["samples"] == 2
    assert bucketed[1]["ts"] == _ts(11, 10)
    assert bucketed[1]["_bucket_ts"] == _ts(11, 0)

    finished = _finish_portfolio_points(bucketed, baseline=100.0)

    assert finished[0]["ts"] == "2026-04-30T10:55:00+00:00"
    assert finished[0]["bucket_start"] == "2026-04-30T10:00:00+00:00"
    assert finished[0]["equity"] == 90.0
    assert finished[0]["pnl_usdt"] == -10.0
    assert finished[0]["drawdown"] == -10.0


def test_raw_portfolio_points_have_no_bucket_start() -> None:
    raw_points = [
        {"ts": _ts(10, 5), "equity": 100.0, "samples": 1, "run_key": "run_a"},
        {"ts": _ts(10, 55), "equity": 101.0, "samples": 1, "run_key": "run_a"},
    ]

    finished = _finish_portfolio_points(
        _bucket_portfolio_points(raw_points, "raw", 2000),
        baseline=100.0,
    )

    assert finished[0]["bucket_start"] is None
    assert finished[1]["bucket_start"] is None
    assert finished[1]["ts"] == "2026-04-30T10:55:00+00:00"


def test_portfolio_curve_ignores_zero_equity_snapshots(db_session) -> None:
    bot = BotInstance(id="bot-test", name="bot-test", environment="test")
    run = Run(
        id="run-test",
        bot_instance_id=bot.id,
        run_key="run_test",
        status="running",
        start_ts=_ts(10, 0),
        start_equity=2746.25,
    )
    db_session.add(bot)
    db_session.add(run)
    db_session.flush()
    db_session.add_all(
        [
            EquitySnapshot(
                run_id=run.id,
                ts=_ts(10, 0),
                equity_usdt=2746.25,
                source="startup",
                source_event_id="eq-start",
            ),
            EquitySnapshot(
                run_id=run.id,
                ts=_ts(10, 30),
                equity_usdt=0.0,
                source="heartbeat",
                source_event_id="eq-bad-zero",
            ),
            EquitySnapshot(
                run_id=run.id,
                ts=_ts(10, 45),
                equity_usdt=2744.88,
                source="heartbeat",
                source_event_id="eq-recovered",
            ),
        ]
    )
    db_session.commit()

    curve = portfolio_equity_curve(
        range_key="all",
        bucket_key="raw",
        basis_key="live",
        max_points=2000,
        db=db_session,
        _=object(),
    )

    equities = [point["equity"] for point in curve["points"]]
    assert equities == [2746.25, 2744.88]
    assert curve["stats"]["max_drawdown"] == pytest.approx(-1.37)
    assert curve["stats"]["max_drawdown_pct"] != -100.0


def test_portfolio_curve_defaults_to_realized_trade_points(db_session) -> None:
    bot = BotInstance(id="bot-realized", name="bot-realized", environment="test")
    run = Run(
        id="run-realized",
        bot_instance_id=bot.id,
        run_key="run_realized",
        status="running",
        start_ts=_ts(10, 0),
        start_equity=1000.0,
    )
    db_session.add(bot)
    db_session.add(run)
    db_session.flush()
    db_session.add_all(
        [
            Trade(
                run_id=run.id,
                pair_key="A/B",
                entry_ts=_ts(10, 5),
                exit_ts=_ts(10, 15),
                pnl_usdt=5.0,
            ),
            Trade(
                run_id=run.id,
                pair_key="C/D",
                entry_ts=_ts(10, 25),
                exit_ts=_ts(10, 35),
                pnl_usdt=-2.0,
            ),
            Trade(
                run_id=run.id,
                pair_key="E/F",
                entry_ts=_ts(10, 45),
                exit_ts=_ts(10, 55),
                pnl_usdt=1.5,
            ),
        ]
    )
    db_session.commit()

    curve = portfolio_equity_curve(
        range_key="all",
        bucket_key="auto",
        max_points=2000,
        db=db_session,
        _=object(),
    )

    assert curve["basis"] == "realized"
    assert curve["source"] == "realized_trades"
    assert curve["bucket"] == "raw"
    assert curve["stats"]["closed_trade_count"] == 3
    assert len(curve["points"]) == 4
    assert [point["equity"] for point in curve["points"]] == [1000.0, 1005.0, 1003.0, 1004.5]
    assert curve["stats"]["change_usdt"] == pytest.approx(4.5)


def test_bucket_portfolio_points_tracks_min_max_equity() -> None:
    raw_points = [
        {"ts": _ts(10, 5), "equity": 100.0, "samples": 1, "run_key": "run_a"},
        {"ts": _ts(10, 30), "equity": 110.0, "samples": 1, "run_key": "run_a"},
        {"ts": _ts(10, 55), "equity": 90.0, "samples": 1, "run_key": "run_a"},
        {"ts": _ts(11, 10), "equity": 95.0, "samples": 1, "run_key": "run_a"},
    ]

    bucketed = _bucket_portfolio_points(raw_points, "hour", 2000)

    assert len(bucketed) == 2
    assert bucketed[0]["_min_equity"] == 90.0
    assert bucketed[0]["_max_equity"] == 110.0
    assert bucketed[1]["_min_equity"] == 95.0
    assert bucketed[1]["_max_equity"] == 95.0


def test_finish_portfolio_points_uses_bucket_max_for_drawdown() -> None:
    raw_points = [
        {"ts": _ts(10, 5), "equity": 100.0, "samples": 1, "run_key": "run_a"},
        {"ts": _ts(10, 30), "equity": 110.0, "samples": 1, "run_key": "run_a"},
        {"ts": _ts(10, 55), "equity": 90.0, "samples": 1, "run_key": "run_a"},
    ]

    bucketed = _bucket_portfolio_points(raw_points, "hour", 2000)
    finished = _finish_portfolio_points(bucketed, baseline=100.0)

    assert finished[0]["equity"] == 90.0
    assert finished[0]["drawdown"] == -20.0
    assert finished[0]["drawdown_pct"] == pytest.approx(-18.182, abs=0.001)


def test_live_basis_stats_match_chart_points(db_session) -> None:
    bot = BotInstance(id="bot-live", name="bot-live", environment="test")
    run = Run(
        id="run-live",
        bot_instance_id=bot.id,
        run_key="run_live",
        status="running",
        start_ts=_ts(10, 0),
        start_equity=1000.0,
    )
    db_session.add(bot)
    db_session.add(run)
    db_session.flush()
    db_session.add_all(
        [
            EquitySnapshot(
                run_id=run.id,
                ts=_ts(10, 5),
                equity_usdt=1000.0,
                source="startup",
                source_event_id="eq-1",
            ),
            EquitySnapshot(
                run_id=run.id,
                ts=_ts(10, 35),
                equity_usdt=1100.0,
                source="heartbeat",
                source_event_id="eq-2",
            ),
            EquitySnapshot(
                run_id=run.id,
                ts=_ts(10, 55),
                equity_usdt=900.0,
                source="heartbeat",
                source_event_id="eq-3",
            ),
            EquitySnapshot(
                run_id=run.id,
                ts=_ts(11, 15),
                equity_usdt=1050.0,
                source="heartbeat",
                source_event_id="eq-4",
            ),
        ]
    )
    db_session.commit()

    curve = portfolio_equity_curve(
        range_key="all",
        bucket_key="hour",
        basis_key="live",
        max_points=2000,
        db=db_session,
        _=object(),
    )

    chart_equities = [point["equity"] for point in curve["points"]]
    assert len(chart_equities) == 2
    assert curve["stats"]["point_count"] == 2
    assert curve["stats"]["raw_point_count"] == 4
    assert curve["stats"]["start_equity"] == chart_equities[0]
    assert curve["stats"]["end_equity"] == chart_equities[-1]
    assert curve["stats"]["min_equity"] == min(chart_equities)
    assert curve["stats"]["max_equity"] == max(chart_equities)


def test_live_basis_stats_use_sliced_points_when_exceeding_max_points(db_session) -> None:
    bot = BotInstance(id="bot-live-slice", name="bot-live-slice", environment="test")
    run = Run(
        id="run-live-slice",
        bot_instance_id=bot.id,
        run_key="run_live_slice",
        status="running",
        start_ts=_ts(10, 0),
        start_equity=1000.0,
    )
    db_session.add(bot)
    db_session.add(run)
    db_session.flush()
    for i in range(5):
        db_session.add(
            EquitySnapshot(
                run_id=run.id,
                ts=_ts(10, i * 10),
                equity_usdt=1000.0 + i * 10,
                source="heartbeat",
                source_event_id=f"eq-{i}",
            )
        )
    db_session.commit()

    curve = portfolio_equity_curve(
        range_key="all",
        bucket_key="raw",
        basis_key="live",
        max_points=3,
        db=db_session,
        _=object(),
    )

    assert len(curve["points"]) == 3
    assert curve["stats"]["point_count"] == 3
    assert curve["stats"]["raw_point_count"] == 5
    assert curve["stats"]["start_equity"] == curve["points"][0]["equity"]
    assert curve["stats"]["end_equity"] == curve["points"][-1]["equity"]
    assert curve["stats"]["min_equity"] == min(point["equity"] for point in curve["points"])
    assert curve["stats"]["max_equity"] == max(point["equity"] for point in curve["points"])


def test_live_basis_empty_data_returns_baseline_point(db_session) -> None:
    bot = BotInstance(id="bot-empty", name="bot-empty", environment="test")
    run = Run(
        id="run-empty",
        bot_instance_id=bot.id,
        run_key="run_empty",
        status="running",
        start_ts=_ts(10, 0),
        start_equity=1000.0,
    )
    db_session.add(bot)
    db_session.add(run)
    db_session.commit()

    curve = portfolio_equity_curve(
        range_key="all",
        bucket_key="raw",
        basis_key="live",
        max_points=2000,
        db=db_session,
        _=object(),
    )

    assert curve["basis"] == "live"
    assert len(curve["points"]) == 1
    assert curve["points"][0]["equity"] == 1000.0
    assert curve["stats"]["point_count"] == 1
    assert curve["stats"]["start_equity"] == 1000.0
    assert curve["stats"]["end_equity"] == 1000.0


def test_realized_basis_empty_data_returns_empty_curve(db_session) -> None:
    bot = BotInstance(id="bot-empty-realized", name="bot-empty-realized", environment="test")
    run = Run(
        id="run-empty-realized",
        bot_instance_id=bot.id,
        run_key="run_empty_realized",
        status="running",
        start_ts=_ts(10, 0),
        start_equity=1000.0,
    )
    db_session.add(bot)
    db_session.add(run)
    db_session.commit()

    curve = portfolio_equity_curve(
        range_key="all",
        bucket_key="auto",
        max_points=2000,
        db=db_session,
        _=object(),
    )

    assert curve["basis"] == "realized"
    assert curve["source"] == "realized_trades"
    assert len(curve["points"]) == 0
    assert curve["stats"]["point_count"] == 0


def test_live_basis_single_point(db_session) -> None:
    bot = BotInstance(id="bot-single", name="bot-single", environment="test")
    run = Run(
        id="run-single",
        bot_instance_id=bot.id,
        run_key="run_single",
        status="running",
        start_ts=_ts(10, 0),
        start_equity=1000.0,
    )
    db_session.add(bot)
    db_session.add(run)
    db_session.flush()
    db_session.add(
        EquitySnapshot(
            run_id=run.id,
            ts=_ts(10, 5),
            equity_usdt=1050.0,
            source="startup",
            source_event_id="eq-1",
        )
    )
    db_session.commit()

    curve = portfolio_equity_curve(
        range_key="all",
        bucket_key="raw",
        basis_key="live",
        max_points=2000,
        db=db_session,
        _=object(),
    )

    assert len(curve["points"]) == 1
    assert curve["points"][0]["equity"] == 1050.0
    assert curve["stats"]["start_equity"] == 1050.0
    assert curve["stats"]["end_equity"] == 1050.0
    assert curve["stats"]["max_drawdown"] == 0.0
    assert curve["stats"]["change_usdt"] == 0.0


def test_range_filter_24h_excludes_old_points(db_session) -> None:
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    recent = now - timedelta(hours=1)
    older = now - timedelta(hours=25)

    bot = BotInstance(id="bot-range", name="bot-range", environment="test")
    run = Run(
        id="run-range",
        bot_instance_id=bot.id,
        run_key="run_range",
        status="running",
        start_ts=older,
        start_equity=1000.0,
    )
    db_session.add(bot)
    db_session.add(run)
    db_session.flush()
    db_session.add_all(
        [
            EquitySnapshot(
                run_id=run.id,
                ts=older,
                equity_usdt=1000.0,
                source="startup",
                source_event_id="eq-old",
            ),
            EquitySnapshot(
                run_id=run.id,
                ts=recent,
                equity_usdt=1100.0,
                source="heartbeat",
                source_event_id="eq-new",
            ),
        ]
    )
    db_session.commit()

    curve = portfolio_equity_curve(
        range_key="24h",
        bucket_key="raw",
        basis_key="live",
        max_points=2000,
        db=db_session,
        _=object(),
    )

    assert len(curve["points"]) == 1
    assert curve["points"][0]["equity"] == 1100.0


def test_day_bucket_aggregates_correctly(db_session) -> None:
    bot = BotInstance(id="bot-day", name="bot-day", environment="test")
    run = Run(
        id="run-day",
        bot_instance_id=bot.id,
        run_key="run_day",
        status="running",
        start_ts=_ts(10, 0),
        start_equity=1000.0,
    )
    db_session.add(bot)
    db_session.add(run)
    db_session.flush()
    db_session.add_all(
        [
            EquitySnapshot(
                run_id=run.id,
                ts=_ts(10, 0),
                equity_usdt=1000.0,
                source="startup",
                source_event_id="eq-1",
            ),
            EquitySnapshot(
                run_id=run.id,
                ts=_ts(12, 0),
                equity_usdt=1100.0,
                source="heartbeat",
                source_event_id="eq-2",
            ),
            EquitySnapshot(
                run_id=run.id,
                ts=_ts(14, 0),
                equity_usdt=900.0,
                source="heartbeat",
                source_event_id="eq-3",
            ),
            EquitySnapshot(
                run_id=run.id,
                ts=_ts(16, 0),
                equity_usdt=1050.0,
                source="heartbeat",
                source_event_id="eq-4",
            ),
        ]
    )
    db_session.commit()

    curve = portfolio_equity_curve(
        range_key="all",
        bucket_key="day",
        basis_key="live",
        max_points=2000,
        db=db_session,
        _=object(),
    )

    assert len(curve["points"]) == 1
    assert curve["bucket"] == "day"
    assert curve["points"][0]["equity"] == 1050.0
    assert curve["points"][0]["samples"] == 4
    assert curve["stats"]["point_count"] == 1


def test_max_drawdown_across_multiple_buckets(db_session) -> None:
    bot = BotInstance(id="bot-dd", name="bot-dd", environment="test")
    run = Run(
        id="run-dd",
        bot_instance_id=bot.id,
        run_key="run_dd",
        status="running",
        start_ts=_ts(10, 0),
        start_equity=1000.0,
    )
    db_session.add(bot)
    db_session.add(run)
    db_session.flush()
    db_session.add_all(
        [
            EquitySnapshot(
                run_id=run.id,
                ts=_ts(10, 0),
                equity_usdt=1000.0,
                source="startup",
                source_event_id="eq-1",
            ),
            EquitySnapshot(
                run_id=run.id,
                ts=_ts(10, 30),
                equity_usdt=1200.0,
                source="heartbeat",
                source_event_id="eq-2",
            ),
            EquitySnapshot(
                run_id=run.id,
                ts=_ts(11, 0),
                equity_usdt=800.0,
                source="heartbeat",
                source_event_id="eq-3",
            ),
            EquitySnapshot(
                run_id=run.id,
                ts=_ts(12, 0),
                equity_usdt=1100.0,
                source="heartbeat",
                source_event_id="eq-4",
            ),
        ]
    )
    db_session.commit()

    curve = portfolio_equity_curve(
        range_key="all",
        bucket_key="hour",
        basis_key="live",
        max_points=2000,
        db=db_session,
        _=object(),
    )

    assert len(curve["points"]) == 3
    assert curve["stats"]["max_drawdown"] == pytest.approx(-400.0)
    assert curve["stats"]["max_drawdown_pct"] == pytest.approx(-33.333, abs=0.001)


def test_realized_basis_with_trades_creates_correct_equity_points(db_session) -> None:
    bot = BotInstance(id="bot-realized-multi", name="bot-realized-multi", environment="test")
    run = Run(
        id="run-realized-multi",
        bot_instance_id=bot.id,
        run_key="run_realized_multi",
        status="running",
        start_ts=_ts(10, 0),
        start_equity=1000.0,
    )
    db_session.add(bot)
    db_session.add(run)
    db_session.flush()
    db_session.add_all(
        [
            Trade(
                run_id=run.id,
                pair_key="A/B",
                entry_ts=_ts(10, 5),
                exit_ts=_ts(10, 15),
                pnl_usdt=10.0,
            ),
            Trade(
                run_id=run.id,
                pair_key="C/D",
                entry_ts=_ts(10, 25),
                exit_ts=_ts(10, 35),
                pnl_usdt=-5.0,
            ),
            Trade(
                run_id=run.id,
                pair_key="E/F",
                entry_ts=_ts(10, 45),
                exit_ts=_ts(10, 55),
                pnl_usdt=20.0,
            ),
        ]
    )
    db_session.commit()

    curve = portfolio_equity_curve(
        range_key="all",
        bucket_key="auto",
        max_points=2000,
        db=db_session,
        _=object(),
    )

    assert curve["basis"] == "realized"
    assert len(curve["points"]) == 4
    expected_equities = [1000.0, 1010.0, 1005.0, 1025.0]
    assert [point["equity"] for point in curve["points"]] == expected_equities
    assert curve["stats"]["start_equity"] == 1000.0
    assert curve["stats"]["end_equity"] == 1025.0
    assert curve["stats"]["change_usdt"] == 25.0
    assert curve["stats"]["max_equity"] == 1025.0
    assert curve["stats"]["min_equity"] == 1000.0
