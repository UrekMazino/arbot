"""Point-in-time curator state lookup for chart replay.

The replay layer must not judge historical candles using today's curator
report. This module only trusts historical transition records, an explicitly
provided point-in-time recomputation callback, or an explicitly marked current
approximate state.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.chart_audit.marker_types import CuratorState


CURATOR_SOURCE_HISTORICAL = "historical"
CURATOR_SOURCE_RECOMPUTED_POINT_IN_TIME = "recomputed_point_in_time"
CURATOR_SOURCE_UNAVAILABLE = "unavailable"
CURATOR_SOURCE_CURRENT_APPROXIMATE = "current_approximate"

DEFAULT_CURATOR_STATE_LOG_PATHS = (
    Path("Strategy/output/pair_universe_curator_state_log.jsonl"),
    Path("Strategy/output/pair_universe_curator_state_log.json"),
    Path("Strategy/output/pair_universe_curator_history.jsonl"),
    Path("Strategy/output/pair_universe_curator_history.json"),
    Path("Execution/state/pair_universe_curator_state_log.jsonl"),
    Path("Execution/state/pair_universe_curator_state_log.json"),
)

CURRENT_APPROXIMATE_WARNING = "Historical curator state unavailable; current approximate state used for replay."
NO_HISTORICAL_LOG_REASON = "No historical curator log found \u2192 mark insufficient_data"


@dataclass(frozen=True)
class CuratorStateAtResult:
    curator_state: CuratorState
    curator_state_source: str
    transition_timestamp: int | None = None
    reason: str | None = None
    warning: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def replay_status(self) -> str | None:
        if self.curator_state == CuratorState.INSUFFICIENT_HISTORY:
            return "insufficient_data"
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "curator_state": self.curator_state.value,
            "curator_state_source": self.curator_state_source,
            "transition_timestamp": self.transition_timestamp,
            "reason": self.reason,
            "warning": self.warning,
            "replay_status": self.replay_status,
            "metadata": dict(self.metadata),
        }


def curator_state_at(
    pair: str,
    timestamp: int | float | datetime | str,
    *,
    historical_events: Iterable[Any] | None = None,
    historical_log_path: str | Path | None = None,
    recompute_fn: Callable[[str, int], CuratorStateAtResult | CuratorState | str | Mapping[str, Any] | None] | None = None,
    current_state: CuratorState | str | None = None,
    allow_current_approximate: bool = False,
) -> CuratorStateAtResult:
    """Return the curator state known for ``pair`` at ``timestamp``."""

    normalized_pair = normalize_pair_key(pair)
    timestamp_value = _coerce_timestamp(timestamp)
    if timestamp_value is None:
        raise ValueError("curator_state_at requires a valid timestamp")
    target_timestamp = int(timestamp_value)

    records = list(historical_events) if historical_events is not None else _load_historical_records(historical_log_path)
    if records:
        transition = _latest_transition_at_or_before(records, normalized_pair, target_timestamp)
        if transition is not None:
            return CuratorStateAtResult(
                curator_state=transition.curator_state,
                curator_state_source=CURATOR_SOURCE_HISTORICAL,
                transition_timestamp=transition.transition_timestamp,
                reason=transition.reason,
                metadata={
                    "pair": normalized_pair,
                    "source": transition.source or CURATOR_SOURCE_HISTORICAL,
                },
            )
        return CuratorStateAtResult(
            curator_state=CuratorState.INSUFFICIENT_HISTORY,
            curator_state_source=CURATOR_SOURCE_UNAVAILABLE,
            reason="No prior curator state transition exists at or before timestamp; insufficient_data.",
            metadata={"pair": normalized_pair},
        )

    if recompute_fn is not None:
        recomputed = _coerce_recomputed_result(recompute_fn(normalized_pair, target_timestamp))
        if recomputed is not None:
            return recomputed

    if allow_current_approximate and current_state is not None:
        return CuratorStateAtResult(
            curator_state=normalize_curator_state(current_state),
            curator_state_source=CURATOR_SOURCE_CURRENT_APPROXIMATE,
            warning=CURRENT_APPROXIMATE_WARNING,
            metadata={"pair": normalized_pair},
        )

    return CuratorStateAtResult(
        curator_state=CuratorState.INSUFFICIENT_HISTORY,
        curator_state_source=CURATOR_SOURCE_UNAVAILABLE,
        reason=NO_HISTORICAL_LOG_REASON,
        metadata={"pair": normalized_pair},
    )


@dataclass(frozen=True)
class _CuratorTransition:
    pair: str
    transition_timestamp: int
    curator_state: CuratorState
    previous_state: CuratorState | None = None
    reason: str | None = None
    source: str | None = None


def _latest_transition_at_or_before(
    records: Iterable[Any],
    pair: str,
    timestamp: int,
) -> _CuratorTransition | None:
    candidates: list[_CuratorTransition] = []
    for record in records:
        transition = _parse_transition(record)
        if transition is None:
            continue
        if not same_pair(transition.pair, pair):
            continue
        if transition.transition_timestamp <= timestamp:
            candidates.append(transition)
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.transition_timestamp)


def _parse_transition(record: Any) -> _CuratorTransition | None:
    pair = _record_pair_key(record)
    timestamp = _coerce_timestamp(
        _get_any(record, "transition_timestamp", "timestamp", "ts", "created_at", "checked_at")
    )
    state_value = _get_any(record, "new_state", "curator_state", "state")
    if state_value is None:
        state_value = _get_any(record, "status")
    if not pair or timestamp is None or state_value is None:
        return None
    try:
        state = normalize_curator_state(state_value)
    except ValueError:
        return None

    previous_state = None
    previous_value = _get_any(record, "previous_state")
    if previous_value is not None:
        try:
            previous_state = normalize_curator_state(previous_value)
        except ValueError:
            previous_state = None

    return _CuratorTransition(
        pair=pair,
        transition_timestamp=int(timestamp),
        curator_state=state,
        previous_state=previous_state,
        reason=_normalize_text(_get_any(record, "reason")),
        source=_normalize_text(_get_any(record, "source")),
    )


def _load_historical_records(historical_log_path: str | Path | None) -> list[Any]:
    paths = [Path(historical_log_path)] if historical_log_path is not None else list(DEFAULT_CURATOR_STATE_LOG_PATHS)
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        records = _read_historical_log(path)
        if records:
            return records
    return []


def _read_historical_log(path: Path) -> list[Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    if not text.strip():
        return []

    if path.suffix.lower() == ".jsonl":
        records = []
        for line in text.splitlines():
            line_text = line.strip()
            if not line_text:
                continue
            try:
                parsed = json.loads(line_text)
            except json.JSONDecodeError:
                continue
            records.append(parsed)
        return records

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, Mapping):
        for key in ("transitions", "events", "records", "history"):
            value = parsed.get(key)
            if isinstance(value, list):
                return value
    return []


def _coerce_recomputed_result(
    value: CuratorStateAtResult | CuratorState | str | Mapping[str, Any] | None,
) -> CuratorStateAtResult | None:
    if value is None:
        return None
    if isinstance(value, CuratorStateAtResult):
        if value.curator_state_source != CURATOR_SOURCE_RECOMPUTED_POINT_IN_TIME:
            return CuratorStateAtResult(
                curator_state=value.curator_state,
                curator_state_source=CURATOR_SOURCE_RECOMPUTED_POINT_IN_TIME,
                transition_timestamp=value.transition_timestamp,
                reason=value.reason,
                warning=value.warning,
                metadata=value.metadata,
            )
        return value
    if isinstance(value, Mapping):
        return CuratorStateAtResult(
            curator_state=normalize_curator_state(value.get("curator_state") or value.get("state")),
            curator_state_source=CURATOR_SOURCE_RECOMPUTED_POINT_IN_TIME,
            transition_timestamp=_optional_int_timestamp(value.get("transition_timestamp") or value.get("timestamp")),
            reason=_normalize_text(value.get("reason")),
            warning=_normalize_text(value.get("warning")),
            metadata=value.get("metadata") if isinstance(value.get("metadata"), Mapping) else {},
        )
    return CuratorStateAtResult(
        curator_state=normalize_curator_state(value),
        curator_state_source=CURATOR_SOURCE_RECOMPUTED_POINT_IN_TIME,
    )


def normalize_curator_state(value: Any) -> CuratorState:
    if isinstance(value, CuratorState):
        return value
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "healthy": CuratorState.TRADABLE,
        "promote": CuratorState.TRADABLE,
        "tradable": CuratorState.TRADABLE,
        "watch": CuratorState.ANALYSIS_ONLY,
        "degraded": CuratorState.ANALYSIS_ONLY,
        "hospital_candidate": CuratorState.ANALYSIS_ONLY,
        "cooldown_candidate": CuratorState.ANALYSIS_ONLY,
        "analysis_only": CuratorState.ANALYSIS_ONLY,
        "excluded": CuratorState.EXCLUDED,
        "removed": CuratorState.EXCLUDED,
        "hospital": CuratorState.HOSPITAL,
        "graveyard": CuratorState.GRAVEYARD,
        "stale": CuratorState.STALE_DATA,
        "stale_data": CuratorState.STALE_DATA,
        "no_data": CuratorState.INSUFFICIENT_HISTORY,
        "insufficient_data": CuratorState.INSUFFICIENT_HISTORY,
        "insufficient_history": CuratorState.INSUFFICIENT_HISTORY,
        "low_liquidity": CuratorState.LOW_LIQUIDITY,
        "curator_low_liquidity": CuratorState.LOW_LIQUIDITY,
    }
    if text in aliases:
        return aliases[text]
    return CuratorState(text)


def normalize_pair_key(pair: Any) -> str:
    if isinstance(pair, (tuple, list)) and len(pair) >= 2:
        return f"{str(pair[0]).strip()}/{str(pair[1]).strip()}"
    text = str(pair or "").strip()
    if "/" in text:
        left, right = text.split("/", 1)
        return f"{left.strip()}/{right.strip()}"
    if "__" in text:
        left, right = text.split("__", 1)
        return f"{left.strip()}/{right.strip()}"
    return text


def same_pair(left: Any, right: Any) -> bool:
    left_key = normalize_pair_key(left)
    right_key = normalize_pair_key(right)
    left_parts = [part for part in left_key.split("/") if part]
    right_parts = [part for part in right_key.split("/") if part]
    if len(left_parts) == 2 and len(right_parts) == 2:
        return set(left_parts) == set(right_parts)
    return left_key == right_key


def _record_pair_key(record: Any) -> str:
    pair_value = _get_any(record, "pair", "pair_key")
    if pair_value:
        return normalize_pair_key(pair_value)
    sym_1 = _get_any(record, "sym_1", "ticker_1")
    sym_2 = _get_any(record, "sym_2", "ticker_2")
    if sym_1 and sym_2:
        return normalize_pair_key((sym_1, sym_2))
    return ""


def _get_any(record: Any, *keys: str) -> Any:
    for key in keys:
        if isinstance(record, Mapping) and key in record:
            return record[key]
        if not isinstance(record, Mapping) and hasattr(record, key):
            return getattr(record, key)
    return None


def _optional_int_timestamp(value: Any) -> int | None:
    timestamp = _coerce_timestamp(value)
    return int(timestamp) if timestamp is not None else None


def _coerce_timestamp(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt_value = value
        if dt_value.tzinfo is None:
            dt_value = dt_value.replace(tzinfo=timezone.utc)
        return float(dt_value.timestamp())
    if isinstance(value, (int, float)):
        parsed = float(value)
        if parsed > 10_000_000_000:
            parsed /= 1000.0
        return parsed
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        try:
            parsed_dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        return _coerce_timestamp(parsed_dt)
    if parsed > 10_000_000_000:
        parsed /= 1000.0
    return parsed


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "CURRENT_APPROXIMATE_WARNING",
    "CURATOR_SOURCE_CURRENT_APPROXIMATE",
    "CURATOR_SOURCE_HISTORICAL",
    "CURATOR_SOURCE_RECOMPUTED_POINT_IN_TIME",
    "CURATOR_SOURCE_UNAVAILABLE",
    "CuratorStateAtResult",
    "NO_HISTORICAL_LOG_REASON",
    "curator_state_at",
    "normalize_curator_state",
    "normalize_pair_key",
    "same_pair",
]
