from __future__ import annotations

import pandas as pd

from Strategy.advanced_pair_ranking import apply_advanced_pair_ranking
from core.config.advanced_ml_config import AdvancedMLConfig


def _pairs() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sym_1": "AAA-USDT-SWAP",
                "sym_2": "BBB-USDT-SWAP",
                "p_value": 0.01,
                "adf_stat": -4.2,
                "hedge_ratio": 1.0,
                "correlation": 0.90,
                "zero_crossing": 8,
                "pair_liquidity_min": 10_000.0,
                "pair_order_capacity_usdt": 20_000.0,
            },
            {
                "sym_1": "CCC-USDT-SWAP",
                "sym_2": "DDD-USDT-SWAP",
                "p_value": 0.04,
                "adf_stat": -3.1,
                "hedge_ratio": 1.5,
                "correlation": 0.70,
                "zero_crossing": 30,
                "pair_liquidity_min": 5_000.0,
                "pair_order_capacity_usdt": 15_000.0,
            },
        ]
    )


def _config(tmp_path, *, live: bool = False) -> AdvancedMLConfig:
    config = AdvancedMLConfig()
    config.pipeline.enabled = live
    config.pipeline.shadow_mode = not live
    config.persistence.model_state_path = str(tmp_path)
    config.ev.warn_when_using_default_spread_edge = False
    return config


def test_advanced_pair_ranking_shadow_adds_columns_without_reordering(tmp_path):
    df = _pairs()

    ranked, summary = apply_advanced_pair_ranking(df, config=_config(tmp_path))

    assert ranked["sym_1"].tolist() == ["AAA-USDT-SWAP", "CCC-USDT-SWAP"]
    assert "advanced_bayes_probability" in ranked.columns
    assert "advanced_bandit_score" in ranked.columns
    assert "advanced_final_score" in ranked.columns
    assert ranked["advanced_shadow_mode"].astype(bool).all()
    assert summary["advanced_pair_ranking"]["mode"] == "shadow"
    assert summary["advanced_pair_ranking"]["live_sort_applied"] is False


def test_advanced_pair_ranking_live_can_sort_after_hard_validation(tmp_path):
    df = _pairs()

    ranked, summary = apply_advanced_pair_ranking(df, config=_config(tmp_path, live=True))

    assert "advanced_final_rank" in ranked.columns
    assert ranked["advanced_rank_live_applied"].astype(bool).all()
    assert summary["advanced_pair_ranking"]["mode"] == "live"
    assert summary["advanced_pair_ranking"]["live_sort_applied"] is True
    assert ranked.iloc[0]["advanced_final_score"] >= ranked.iloc[-1]["advanced_final_score"]


def test_advanced_pair_ranking_invalid_row_is_not_scored_as_valid(tmp_path):
    df = _pairs()
    df.loc[0, "hedge_ratio"] = 0.0

    ranked, summary = apply_advanced_pair_ranking(df, config=_config(tmp_path))

    assert ranked.loc[0, "advanced_final_score"] == 0.0
    assert ranked.loc[0, "advanced_bayes_grade"] == "D"
    assert summary["advanced_pair_ranking"]["invalid_rows_skipped"] == 1
