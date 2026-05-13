from __future__ import annotations

import json
import math

from core.dashboard.contracts import (
    AnalyticsSummary,
    DashboardCacheMeta,
    DashboardTag,
    PairSummary,
    PortfolioSummary,
    SUPPORTED_DASHBOARD_TAGS,
    TradeSummary,
)


PAIR = "AAA-USDT-SWAP/BBB-USDT-SWAP"


def test_pair_summary_serializes_nested_trades_and_tags() -> None:
    best_trade = TradeSummary(
        trade_id="trade-best",
        pair=PAIR,
        side="BUY_SPREAD",
        entry_time=1_715_000_000,
        exit_time=1_715_000_300,
        entry_z=-2.4,
        exit_z=-0.2,
        hold_seconds=300.0,
        pnl_usdt=12.5,
        fees_usdt=0.3,
        slippage_usdt=0.1,
        exit_reason="z_reversion",
        entry_hedge_ratio=1.2,
        exit_hedge_ratio=1.25,
        hedge_ratio_drift_pct=0.0416667,
        regime_at_entry="mean_reverting",
        final_rank_score_at_entry=0.78,
        bayesian_posterior_at_entry=0.69,
    )
    worst_trade = TradeSummary(trade_id="trade-worst", pair=PAIR, pnl_usdt=-4.0)
    summary = PairSummary(
        pair=PAIR,
        status="stable",
        total_trades=2,
        net_pnl_usdt=8.5,
        block_reason_counts={"pair_in_hospital": 2},
        best_trade=best_trade,
        worst_trade=worst_trade,
        tags=[DashboardTag.ELITE, "warning", "warning"],
    )

    payload = summary.to_dict()

    assert payload["pair"] == PAIR
    assert payload["best_trade"]["trade_id"] == "trade-best"
    assert payload["best_trade"]["final_rank_score_at_entry"] == 0.78
    assert payload["worst_trade"]["pnl_usdt"] == -4.0
    assert payload["block_reason_counts"] == {"pair_in_hospital": 2}
    assert payload["tags"] == ["elite", "warning"]
    json.dumps(payload)


def test_dashboard_contracts_default_to_null_or_empty_values() -> None:
    pair = PairSummary(pair=PAIR)
    portfolio = PortfolioSummary()
    analytics = AnalyticsSummary()

    pair_payload = pair.to_dict()
    portfolio_payload = portfolio.to_dict()
    analytics_payload = analytics.to_dict()

    assert pair_payload["net_pnl_usdt"] is None
    assert pair_payload["block_reason_counts"] == {}
    assert pair_payload["best_trade"] is None
    assert pair_payload["tags"] == []
    assert portfolio_payload["total_equity_usdt"] is None
    assert portfolio_payload["open_positions"] == []
    assert portfolio_payload["cache"]["refresh_supported"] is True
    assert analytics_payload["performance"] == {}
    assert analytics_payload["pnl_timeseries"] == []
    assert analytics_payload["pair_leaderboards"] == []


def test_dashboard_tag_enum_matches_supported_tag_strings() -> None:
    assert set(SUPPORTED_DASHBOARD_TAGS) == {tag.value for tag in DashboardTag}
    for expected in (
        "elite",
        "stable",
        "warning",
        "hospital",
        "graveyard",
        "high_drift",
        "high_slippage",
        "good_reverter",
        "bad_executor",
        "high_break_risk",
        "profitable",
        "losing",
    ):
        assert expected in SUPPORTED_DASHBOARD_TAGS


def test_dashboard_cache_meta_serialization() -> None:
    payload = DashboardCacheMeta(
        cache_hit=True,
        generated_at=1_715_000_000.5,
        ttl_seconds=60,
        refresh_supported=False,
    ).to_dict()

    assert payload == {
        "cache_hit": True,
        "generated_at": 1_715_000_000.5,
        "ttl_seconds": 60,
        "refresh_supported": False,
    }


def test_non_finite_numeric_values_serialize_as_null() -> None:
    payload = PairSummary(pair=PAIR, net_pnl_usdt=math.nan).to_dict()

    assert payload["net_pnl_usdt"] is None
