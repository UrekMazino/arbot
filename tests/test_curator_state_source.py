from __future__ import annotations

import json

from core.chart_audit.curator_state_source import (
    CURRENT_APPROXIMATE_WARNING,
    CURATOR_SOURCE_CURRENT_APPROXIMATE,
    CURATOR_SOURCE_HISTORICAL,
    CURATOR_SOURCE_RECOMPUTED_POINT_IN_TIME,
    CURATOR_SOURCE_UNAVAILABLE,
    NO_HISTORICAL_LOG_REASON,
    CuratorStateAtResult,
    curator_state_at,
)
from core.chart_audit.marker_types import CuratorState


def test_curator_state_at_uses_exact_historical_transition() -> None:
    result = curator_state_at(
        "AAA-USDT-SWAP/BBB-USDT-SWAP",
        200,
        historical_events=[
            {
                "pair": "AAA-USDT-SWAP/BBB-USDT-SWAP",
                "transition_timestamp": 100,
                "new_state": "analysis_only",
            },
            {
                "pair": "AAA-USDT-SWAP/BBB-USDT-SWAP",
                "transition_timestamp": 200,
                "new_state": "tradable",
                "reason": "passed validation",
            },
        ],
    )

    assert result.curator_state == CuratorState.TRADABLE
    assert result.curator_state_source == CURATOR_SOURCE_HISTORICAL
    assert result.transition_timestamp == 200
    assert result.reason == "passed validation"


def test_curator_state_at_uses_latest_known_state_before_timestamp() -> None:
    result = curator_state_at(
        "AAA-USDT-SWAP/BBB-USDT-SWAP",
        250,
        historical_events=[
            {
                "pair": "AAA-USDT-SWAP/BBB-USDT-SWAP",
                "transition_timestamp": 100,
                "new_state": "analysis_only",
            },
            {
                "pair": "AAA-USDT-SWAP/BBB-USDT-SWAP",
                "transition_timestamp": 200,
                "new_state": "hospital",
            },
            {
                "pair": "AAA-USDT-SWAP/BBB-USDT-SWAP",
                "transition_timestamp": 300,
                "new_state": "tradable",
            },
        ],
    )

    assert result.curator_state == CuratorState.HOSPITAL
    assert result.curator_state_source == CURATOR_SOURCE_HISTORICAL
    assert result.transition_timestamp == 200


def test_curator_state_at_returns_insufficient_history_when_no_prior_state_exists() -> None:
    result = curator_state_at(
        "AAA-USDT-SWAP/BBB-USDT-SWAP",
        99,
        historical_events=[
            {
                "pair": "AAA-USDT-SWAP/BBB-USDT-SWAP",
                "transition_timestamp": 100,
                "new_state": "tradable",
            },
        ],
    )

    assert result.curator_state == CuratorState.INSUFFICIENT_HISTORY
    assert result.curator_state_source == CURATOR_SOURCE_UNAVAILABLE
    assert result.replay_status == "insufficient_data"
    assert "No prior curator state transition" in str(result.reason)


def test_curator_state_at_missing_log_falls_back_to_insufficient_data(tmp_path) -> None:
    result = curator_state_at(
        "AAA-USDT-SWAP/BBB-USDT-SWAP",
        200,
        historical_log_path=tmp_path / "missing_curator_log.jsonl",
    )

    assert result.curator_state == CuratorState.INSUFFICIENT_HISTORY
    assert result.curator_state_source == CURATOR_SOURCE_UNAVAILABLE
    assert result.reason == NO_HISTORICAL_LOG_REASON
    assert result.replay_status == "insufficient_data"


def test_curator_state_at_does_not_use_current_state_silently(tmp_path) -> None:
    result = curator_state_at(
        "AAA-USDT-SWAP/BBB-USDT-SWAP",
        200,
        historical_log_path=tmp_path / "missing_curator_log.jsonl",
        current_state=CuratorState.TRADABLE,
    )

    assert result.curator_state == CuratorState.INSUFFICIENT_HISTORY
    assert result.curator_state_source == CURATOR_SOURCE_UNAVAILABLE
    assert result.reason == NO_HISTORICAL_LOG_REASON


def test_curator_state_at_can_explicitly_label_current_state_as_approximate(tmp_path) -> None:
    result = curator_state_at(
        "AAA-USDT-SWAP/BBB-USDT-SWAP",
        200,
        historical_log_path=tmp_path / "missing_curator_log.jsonl",
        current_state=CuratorState.TRADABLE,
        allow_current_approximate=True,
    )

    assert result.curator_state == CuratorState.TRADABLE
    assert result.curator_state_source == CURATOR_SOURCE_CURRENT_APPROXIMATE
    assert result.warning == CURRENT_APPROXIMATE_WARNING


def test_curator_state_at_uses_recomputed_point_in_time_source_when_provided(tmp_path) -> None:
    def recompute(pair: str, timestamp: int) -> dict[str, object]:
        assert pair == "AAA-USDT-SWAP/BBB-USDT-SWAP"
        assert timestamp == 200
        return {
            "curator_state": "low_liquidity",
            "reason": "point-in-time recompute",
            "metadata": {"window_end": timestamp},
        }

    result = curator_state_at(
        "AAA-USDT-SWAP/BBB-USDT-SWAP",
        200,
        historical_log_path=tmp_path / "missing_curator_log.jsonl",
        recompute_fn=recompute,
    )

    assert result.curator_state == CuratorState.LOW_LIQUIDITY
    assert result.curator_state_source == CURATOR_SOURCE_RECOMPUTED_POINT_IN_TIME
    assert result.reason == "point-in-time recompute"
    assert result.metadata["window_end"] == 200


def test_curator_state_at_reads_jsonl_historical_log_and_matches_reversed_pair(tmp_path) -> None:
    log_path = tmp_path / "curator_state_log.jsonl"
    records = [
        {
            "sym_1": "AAA-USDT-SWAP",
            "sym_2": "BBB-USDT-SWAP",
            "transition_timestamp": 100,
            "new_state": "analysis_only",
        },
        {
            "sym_1": "AAA-USDT-SWAP",
            "sym_2": "BBB-USDT-SWAP",
            "transition_timestamp": 180,
            "new_state": "tradable",
            "source": "pair_universe_curator",
        },
    ]
    log_path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")

    result = curator_state_at(
        "BBB-USDT-SWAP/AAA-USDT-SWAP",
        200,
        historical_log_path=log_path,
    )

    assert result.curator_state == CuratorState.TRADABLE
    assert result.curator_state_source == CURATOR_SOURCE_HISTORICAL
    assert result.transition_timestamp == 180
    assert result.metadata["source"] == "pair_universe_curator"


def test_curator_state_result_serializes_for_chart_api() -> None:
    result = CuratorStateAtResult(
        curator_state=CuratorState.INSUFFICIENT_HISTORY,
        curator_state_source=CURATOR_SOURCE_UNAVAILABLE,
        reason=NO_HISTORICAL_LOG_REASON,
    )

    payload = result.to_dict()

    assert payload["curator_state"] == "insufficient_history"
    assert payload["curator_state_source"] == "unavailable"
    assert payload["replay_status"] == "insufficient_data"
