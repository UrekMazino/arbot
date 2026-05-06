"""Advanced pair ranking bridge for Strategy pair supply.

Only hard-valid rows from the existing discovery pipeline are converted into
ValidPairCandidate objects. In shadow mode this adds diagnostics without
changing the canonical pair order; live sorting requires explicit advanced ML
live mode.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.bayes.bayesian_pair_scorer import BayesianPairScorer  # noqa: E402
from core.config.advanced_ml_config import AdvancedMLConfig, load_advanced_ml_config_from_env  # noqa: E402
from core.features.feature_schema import FeatureSchema, NamedFeatureVector  # noqa: E402
from core.online_learning.linucb import BanditContext, LinUCBContextualBandit  # noqa: E402
from core.ranking.final_ranker import FinalRanker  # noqa: E402
from core.regime.regime_types import RegimeName  # noqa: E402
from core.storage.model_state_store import ModelStateStore, resolve_model_state_path  # noqa: E402


FEATURE_NAMES = (
    "p_value_quality",
    "zero_crossing_quality",
    "correlation_quality",
    "liquidity_quality",
    "capacity_quality",
    "hedge_ratio_quality",
    "adf_quality",
    "reputation_quality",
)


@dataclass(frozen=True)
class PairIdentity:
    key: str
    sym_1: str
    sym_2: str


@dataclass(frozen=True)
class HardValidationResult:
    is_valid: bool
    p_value: float | None = None
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidPairCandidate:
    pair: PairIdentity
    hard_validation: HardValidationResult
    pair_features: dict[str, float]
    pair_state: str = "stable"


@dataclass(frozen=True)
class RegimeProxy:
    regime: RegimeName
    confidence: float
    break_risk: float
    features: dict[str, float]


def apply_advanced_pair_ranking(
    df_coint: pd.DataFrame,
    *,
    summary: dict[str, Any] | None = None,
    config: AdvancedMLConfig | None = None,
    logger: Any | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    cfg = config or load_advanced_ml_config_from_env()
    runtime_mode = _runtime_mode(cfg)
    output_summary = dict(summary or {})
    if df_coint is None or df_coint.empty:
        output_summary["advanced_pair_ranking"] = {
            "mode": runtime_mode,
            "scored_pairs": 0,
            "live_sort_applied": False,
        }
        return df_coint.copy() if df_coint is not None else pd.DataFrame(), output_summary
    if runtime_mode == "off":
        output_summary["advanced_pair_ranking"] = {
            "mode": "off",
            "scored_pairs": 0,
            "live_sort_applied": False,
        }
        return df_coint.copy(), output_summary

    output = df_coint.copy()
    schema = FeatureSchema(
        FEATURE_NAMES,
        feature_schema_version=cfg.features.feature_schema_version,
        reject_nan_features=cfg.features.reject_nan_features,
    )
    store = ModelStateStore(
        resolve_model_state_path(cfg.persistence.model_state_path),
        atomic_write=cfg.persistence.atomic_write,
        corrupted_state_policy=cfg.persistence.corrupted_state_policy,
    )
    bayes = _load_bayes(store, cfg)
    bandit = _load_bandit(store, cfg, schema)
    ranker = FinalRanker(cfg)

    scored_rows: list[dict[str, Any]] = []
    invalid_rows = 0
    for idx, row in output.iterrows():
        candidate = _candidate_from_row(row)
        if not candidate.hard_validation.is_valid:
            invalid_rows += 1
            scored_rows.append(
                {
                    "index": idx,
                    "advanced_shadow_mode": runtime_mode == "shadow",
                    "advanced_rank_live_applied": False,
                    "advanced_bayes_probability": 0.0,
                    "advanced_bayes_grade": "D",
                    "advanced_bandit_score": 0.0,
                    "advanced_final_score": 0.0,
                    "advanced_rank_reason": "failed hard validation",
                }
            )
            continue

        vector = NamedFeatureVector(schema, np.asarray(_feature_values(candidate), dtype=float))
        regime = _regime_proxy(candidate)
        bayes_score = bayes.score(candidate, regime_result=regime)
        bandit_result = bandit.rank(BanditContext(pair=candidate.pair, features=vector))
        final_rank = ranker.rank(
            candidate,
            regime_result=regime,
            bayesian_score=bayes_score,
            bandit_result=bandit_result,
            reputation_state=candidate.pair_state,
        )
        scored_rows.append(
            {
                "index": idx,
                "advanced_shadow_mode": runtime_mode == "shadow",
                "advanced_rank_live_applied": runtime_mode == "live",
                "advanced_bayes_probability": bayes_score.posterior_good_probability,
                "advanced_bayes_grade": bayes_score.quality_grade,
                "advanced_bandit_score": bandit_result.final_rank_score,
                "advanced_final_score": final_rank.final_score,
                "advanced_rank_reason": "|".join(final_rank.reasons or []),
            }
        )

    for item in scored_rows:
        idx = item.pop("index")
        for key, value in item.items():
            output.loc[idx, key] = value

    scored_count = int(len(scored_rows) - invalid_rows)
    if "advanced_final_score" in output.columns:
        score_series = pd.to_numeric(output["advanced_final_score"], errors="coerce").fillna(0.0)
        rank_series = score_series.rank(method="first", ascending=False).astype(int)
        output["advanced_final_rank"] = rank_series

    live_sort_applied = runtime_mode == "live" and "advanced_final_score" in output.columns
    if live_sort_applied:
        output = output.sort_values(
            by=["advanced_final_score", "zero_crossing", "p_value"],
            ascending=[False, False, True],
            kind="stable",
        ).copy()

    try:
        bayes.save_state(store)
        bandit.save_state(store)
    except Exception as exc:
        if logger is not None:
            logger.warning("Advanced pair ranking state save failed: %s", exc)

    top_pair = None
    if not output.empty:
        first = output.iloc[0]
        top_pair = f"{first.get('sym_1')}/{first.get('sym_2')}"
    output_summary["advanced_pair_ranking"] = {
        "mode": runtime_mode,
        "scored_pairs": scored_count,
        "invalid_rows_skipped": invalid_rows,
        "live_sort_applied": live_sort_applied,
        "top_pair": top_pair,
        "feature_schema_version": cfg.features.feature_schema_version,
    }
    if logger is not None:
        logger.info("Advanced pair ranking summary: %s", output_summary["advanced_pair_ranking"])
    return output, output_summary


def _runtime_mode(config: AdvancedMLConfig) -> str:
    if config.pipeline.enabled and not config.pipeline.shadow_mode:
        return "live"
    if config.pipeline.shadow_mode:
        return "shadow"
    return "off"


def _load_bayes(store: ModelStateStore, config: AdvancedMLConfig) -> BayesianPairScorer:
    path = store.path_for("bayesian_pair_scorer")
    scorer = BayesianPairScorer(config)
    if path.exists():
        scorer.load_state(store)
    return scorer


def _load_bandit(
    store: ModelStateStore,
    config: AdvancedMLConfig,
    schema: FeatureSchema,
) -> LinUCBContextualBandit:
    path = store.path_for("linucb")
    bandit = LinUCBContextualBandit(config, schema=schema)
    if path.exists():
        bandit.load_state(store)
    return bandit


def _candidate_from_row(row: pd.Series) -> ValidPairCandidate:
    sym_1 = str(row.get("sym_1") or "").strip().upper()
    sym_2 = str(row.get("sym_2") or "").strip().upper()
    pair = PairIdentity(key=_pair_key(sym_1, sym_2), sym_1=sym_1, sym_2=sym_2)
    hard_valid, reasons = _hard_valid_row(row)
    features = {
        "p_value": _safe_float(row.get("p_value"), 1.0),
        "zero_crossings": _safe_float(row.get("zero_crossing"), 0.0),
        "correlation": _safe_float(row.get("correlation"), 0.0),
        "hedge_ratio": _safe_float(row.get("hedge_ratio"), 0.0),
        "adf_stat": _safe_float(row.get("adf_stat"), 0.0),
        "liquidity_score": _liquidity_quality(row),
        "pair_order_capacity_usdt": _safe_float(row.get("pair_order_capacity_usdt"), 0.0),
        "break_risk": 0.0 if hard_valid else 1.0,
        "slippage_risk": 0.0,
        "liquidity_stress": 1.0 - _liquidity_quality(row),
        "hedge_ratio_drift_risk": 1.0 - _hedge_ratio_quality(row),
    }
    return ValidPairCandidate(
        pair=pair,
        hard_validation=HardValidationResult(
            is_valid=hard_valid,
            p_value=features["p_value"],
            reasons=tuple(reasons),
        ),
        pair_features=features,
        pair_state=str(row.get("pair_state") or "stable").strip().lower() or "stable",
    )


def _hard_valid_row(row: pd.Series) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not str(row.get("sym_1") or "").strip() or not str(row.get("sym_2") or "").strip():
        reasons.append("missing_symbol")
    p_value = _safe_float(row.get("p_value"), math.nan)
    if not math.isfinite(p_value):
        reasons.append("missing_p_value")
    zero_crossing = _safe_float(row.get("zero_crossing"), math.nan)
    if not math.isfinite(zero_crossing) or zero_crossing < 0:
        reasons.append("invalid_zero_crossing")
    hedge_ratio = _safe_float(row.get("hedge_ratio"), math.nan)
    if not math.isfinite(hedge_ratio) or hedge_ratio == 0:
        reasons.append("invalid_hedge_ratio")
    return not reasons, reasons


def _feature_values(candidate: ValidPairCandidate) -> tuple[float, ...]:
    features = candidate.pair_features
    return (
        _p_value_quality(features.get("p_value")),
        _zero_crossing_quality(features.get("zero_crossings")),
        _correlation_quality(features.get("correlation")),
        _clamp01(float(features.get("liquidity_score", 0.0))),
        _capacity_quality(features.get("pair_order_capacity_usdt")),
        _hedge_ratio_quality(features),
        _adf_quality(features.get("adf_stat")),
        _reputation_quality(candidate.pair_state),
    )


def _regime_proxy(candidate: ValidPairCandidate) -> RegimeProxy:
    features = candidate.pair_features
    p_quality = _p_value_quality(features.get("p_value"))
    crossing_quality = _zero_crossing_quality(features.get("zero_crossings"))
    liquidity = _clamp01(float(features.get("liquidity_score", 1.0)))
    confidence = _clamp01(0.45 * p_quality + 0.35 * crossing_quality + 0.20 * liquidity)
    if confidence >= 0.65:
        regime = RegimeName.MEAN_REVERTING
    elif liquidity < 0.25:
        regime = RegimeName.LIQUIDITY_STRESS
    else:
        regime = RegimeName.UNKNOWN
    break_risk = _clamp01(
        0.55 * (1.0 - p_quality)
        + 0.25 * (1.0 - crossing_quality)
        + 0.20 * (1.0 - liquidity)
    )
    return RegimeProxy(
        regime=regime,
        confidence=confidence,
        break_risk=break_risk,
        features={
            "break_risk": break_risk,
            "slippage_risk": 0.0,
            "liquidity_stress": 1.0 - liquidity,
            "hedge_ratio_drift_risk": 1.0 - _hedge_ratio_quality(features),
        },
    )


def _pair_key(sym_1: str, sym_2: str) -> str:
    return "/".join(sorted((sym_1, sym_2)))


def _safe_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _p_value_quality(value: Any) -> float:
    p_value = _safe_float(value, 1.0)
    if p_value <= 0:
        return 1.0
    return _clamp01(1.0 - p_value / 0.15)


def _zero_crossing_quality(value: Any) -> float:
    return _clamp01(_safe_float(value, 0.0) / 50.0)


def _correlation_quality(value: Any) -> float:
    return _clamp01((abs(_safe_float(value, 0.0)) - 0.50) / 0.50)


def _liquidity_quality(row: pd.Series) -> float:
    liquidity = _safe_float(row.get("pair_liquidity_min"), 0.0)
    return _clamp01(math.log10(max(liquidity, 1.0)) / 5.0)


def _capacity_quality(value: Any) -> float:
    capacity = _safe_float(value, 0.0)
    return _clamp01(math.log10(max(capacity, 1.0)) / 5.0)


def _hedge_ratio_quality(row_or_features: Any) -> float:
    if isinstance(row_or_features, dict):
        raw = row_or_features.get("hedge_ratio")
    else:
        raw = row_or_features.get("hedge_ratio")
    hedge_ratio = abs(_safe_float(raw, 0.0))
    if hedge_ratio <= 0:
        return 0.0
    return _clamp01(1.0 - abs(math.log(max(hedge_ratio, 1e-9))) / math.log(5.0))


def _adf_quality(value: Any) -> float:
    adf = _safe_float(value, 0.0)
    return _clamp01(abs(min(adf, 0.0)) / 5.0)


def _reputation_quality(state: str) -> float:
    normalized = str(state or "stable").strip().lower()
    if normalized == "elite":
        return 1.0
    if normalized == "stable":
        return 0.85
    if normalized == "warning":
        return 0.55
    if normalized == "hospital":
        return 0.20
    if normalized == "graveyard":
        return 0.0
    return 0.75


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


__all__ = [
    "FEATURE_NAMES",
    "HardValidationResult",
    "PairIdentity",
    "RegimeProxy",
    "ValidPairCandidate",
    "apply_advanced_pair_ranking",
]
