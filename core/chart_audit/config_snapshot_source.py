"""Point-in-time bot config lookup for chart replay.

Replay must not receive the full live config object. This module returns only
the replay-relevant fields captured in ReplayConfigSnapshot and labels current
fallback values as approximate.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.chart_audit.replay_snapshot import ReplayConfigSnapshot


CONFIG_SOURCE_HISTORICAL = "historical"
CONFIG_SOURCE_CURRENT_APPROXIMATE = "current_approximate"
CURRENT_CONFIG_WARNING = "Historical config unavailable; current config used for replay."

DEFAULT_CONFIG_VERSION_LOG_PATHS = (
    Path("Execution/state/config_version_log.jsonl"),
    Path("Execution/state/config_version_log.json"),
    Path("Execution/state/config_history.jsonl"),
    Path("Execution/state/config_history.json"),
    Path("Platform/runtime/config_version_log.jsonl"),
    Path("Platform/runtime/config_version_log.json"),
)


@dataclass(frozen=True)
class _HistoricalConfigRecord:
    activated_at: int
    snapshot: ReplayConfigSnapshot


def config_at(
    timestamp: int | float | datetime | str,
    *,
    historical_configs: Iterable[Any] | None = None,
    historical_log_path: str | Path | None = None,
    current_config: Mapping[str, Any] | Any | None = None,
    env: Mapping[str, str] | None = None,
) -> ReplayConfigSnapshot:
    """Return the replay-relevant bot config active at ``timestamp``.

    Historical config records are preferred. If no historical version is
    available for the timestamp, the current config is copied into a minimal
    ReplayConfigSnapshot and marked as ``current_approximate``.
    """

    target_timestamp = _required_timestamp(timestamp)
    records = (
        list(historical_configs)
        if historical_configs is not None
        else _load_historical_config_records(historical_log_path)
    )
    if records:
        historical = _latest_config_at_or_before(records, target_timestamp)
        if historical is not None:
            return historical

    return current_config_snapshot(current_config=current_config, env=env)


def current_config_snapshot(
    *,
    current_config: Mapping[str, Any] | Any | None = None,
    env: Mapping[str, str] | None = None,
) -> ReplayConfigSnapshot:
    """Copy the current config into the minimal replay snapshot contract."""

    env_source = os.environ if env is None else env
    return ReplayConfigSnapshot(
        config_version=str(_first_extracted(current_config, ("config_version",), ("version",)) or "current"),
        config_source=CONFIG_SOURCE_CURRENT_APPROXIMATE,
        entry_z_threshold=_number_from_config_or_env(
            current_config,
            env_source,
            aliases=(
                ("entry_z_threshold",),
                ("entry_z",),
                ("signals", "entry_z"),
            ),
            env_names=("STATBOT_ENTRY_Z",),
            default=2.0,
        ),
        exit_z_threshold=_number_from_config_or_env(
            current_config,
            env_source,
            aliases=(
                ("exit_z_threshold",),
                ("exit_z",),
                ("signals", "exit_z"),
            ),
            env_names=("STATBOT_EXIT_Z",),
            default=0.35,
        ),
        persistence_candles=int(
            _number_from_config_or_env(
                current_config,
                env_source,
                aliases=(
                    ("persistence_candles",),
                    ("min_persist_bars",),
                    ("signals", "min_persist_bars"),
                ),
                env_names=("STATBOT_MIN_PERSIST_BARS",),
                default=4.0,
            )
        ),
        max_hold_seconds=_current_max_hold_seconds(current_config, env_source),
        min_zero_crossings=int(
            _number_from_config_or_env(
                current_config,
                env_source,
                aliases=(
                    ("min_zero_crossings",),
                    ("zero_crossings_min",),
                    ("signals", "zero_crossings_min"),
                    ("strategy", "min_zero_crossings"),
                ),
                env_names=("STATBOT_ZERO_CROSSINGS_MIN", "STATBOT_STRATEGY_MIN_ZERO_CROSSINGS"),
                default=15.0,
            )
        ),
        min_liquidity_score=_optional_number_from_config_or_env(
            current_config,
            env_source,
            aliases=(
                ("min_liquidity_score",),
                ("exit", "min_liquidity_score"),
            ),
            env_names=("STATBOT_EXIT_MIN_LIQUIDITY_SCORE",),
            default=0.10,
        ),
        max_orderbook_age_ms=_optional_number_from_config_or_env(
            current_config,
            env_source,
            aliases=(
                ("max_orderbook_age_ms",),
                ("max_book_age_ms",),
                ("advanced_ml", "max_book_age_ms"),
                ("microstructure", "max_book_age_ms"),
            ),
            env_names=("STATBOT_EXIT_MAX_BOOK_AGE_MS", "STATBOT_ADVANCED_ML_MAX_BOOK_AGE_MS"),
            default=1500.0,
        ),
        max_spread_bps=_optional_number_from_config_or_env(
            current_config,
            env_source,
            aliases=(
                ("max_spread_bps",),
                ("wide_spread_bps",),
                ("advanced_ml", "wide_spread_bps"),
                ("microstructure", "wide_spread_bps"),
            ),
            env_names=("STATBOT_REPLAY_MAX_SPREAD_BPS", "STATBOT_ADVANCED_ML_WIDE_SPREAD_BPS"),
            default=5.0,
        ),
        max_slippage_bps=_optional_number_from_config_or_env(
            current_config,
            env_source,
            aliases=(
                ("max_slippage_bps",),
                ("max_allowed_slippage_bps",),
                ("microstructure", "max_allowed_slippage_bps"),
            ),
            env_names=("STATBOT_ADVANCED_ML_MAX_ALLOWED_SLIPPAGE_BPS",),
            default=8.0,
        ),
        hedge_ratio_sizing_enabled=_bool_from_config_or_env(
            current_config,
            env_source,
            aliases=(
                ("hedge_ratio_sizing_enabled",),
                ("hedge_sizing", "enabled"),
                ("hedge_ratio", "sizing_enabled"),
                ("strategy", "hedge_ratio_sizing_enabled"),
            ),
            env_names=("STATBOT_HEDGE_RATIO_SIZING_ENABLED",),
            default=False,
        ),
        hedge_sizing_mode=_text_from_config_or_env(
            current_config,
            env_source,
            aliases=(
                ("hedge_sizing_mode",),
                ("hedge_sizing", "mode"),
                ("hedge_ratio", "sizing_mode"),
                ("strategy", "hedge_sizing_mode"),
            ),
            env_names=("STATBOT_HEDGE_SIZING_MODE",),
            default="equal_notional",
        ),
        min_hedge_ratio=_number_from_config_or_env(
            current_config,
            env_source,
            aliases=(("min_hedge_ratio",), ("hedge_ratio", "min"), ("strategy", "min_hedge_ratio")),
            env_names=("STATBOT_MIN_HEDGE_RATIO",),
            default=0.20,
        ),
        max_hedge_ratio=_number_from_config_or_env(
            current_config,
            env_source,
            aliases=(("max_hedge_ratio",), ("hedge_ratio", "max"), ("strategy", "max_hedge_ratio")),
            env_names=("STATBOT_MAX_HEDGE_RATIO",),
            default=5.00,
        ),
        reject_negative_hedge_ratio=_bool_from_config_or_env(
            current_config,
            env_source,
            aliases=(
                ("reject_negative_hedge_ratio",),
                ("hedge_ratio", "reject_negative"),
                ("strategy", "reject_negative_hedge_ratio"),
            ),
            env_names=("STATBOT_REJECT_NEGATIVE_HEDGE_RATIO",),
            default=True,
        ),
        max_hedge_sizing_error_pct=_number_from_config_or_env(
            current_config,
            env_source,
            aliases=(
                ("max_hedge_sizing_error_pct",),
                ("hedge_sizing", "max_error_pct"),
                ("strategy", "max_hedge_sizing_error_pct"),
            ),
            env_names=("STATBOT_MAX_HEDGE_SIZING_ERROR_PCT",),
            default=0.10,
        ),
        max_hedge_ratio_drift_pct=_number_from_config_or_env(
            current_config,
            env_source,
            aliases=(
                ("max_hedge_ratio_drift_pct",),
                ("hedge_ratio", "max_drift_pct"),
                ("strategy", "max_hedge_ratio_drift_pct"),
            ),
            env_names=("STATBOT_MAX_HEDGE_RATIO_DRIFT_PCT",),
            default=0.20,
        ),
        severe_hedge_ratio_drift_pct=_number_from_config_or_env(
            current_config,
            env_source,
            aliases=(
                ("severe_hedge_ratio_drift_pct",),
                ("hedge_ratio", "severe_drift_pct"),
                ("strategy", "severe_hedge_ratio_drift_pct"),
            ),
            env_names=("STATBOT_SEVERE_HEDGE_RATIO_DRIFT_PCT",),
            default=0.35,
        ),
        min_cointegration_window=int(
            _number_from_config_or_env(
                current_config,
                env_source,
                aliases=(
                    ("min_cointegration_window",),
                    ("cointegration", "min_window"),
                    ("strategy", "min_cointegration_window"),
                ),
                env_names=("STATBOT_MIN_COINTEGRATION_WINDOW",),
                default=120.0,
            )
        ),
        warning=CURRENT_CONFIG_WARNING,
    )


def _latest_config_at_or_before(records: Iterable[Any], timestamp: int) -> ReplayConfigSnapshot | None:
    candidates: list[_HistoricalConfigRecord] = []
    for record in records:
        parsed = _parse_historical_config_record(record)
        if parsed is None:
            continue
        if parsed.activated_at <= timestamp:
            candidates.append(parsed)
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.activated_at).snapshot


def _parse_historical_config_record(record: Any) -> _HistoricalConfigRecord | None:
    payload = _record_payload(record)
    activated_at = _coerce_timestamp(
        _first_extracted(record, ("activated_at",), ("activation_ts",), ("timestamp",), ("ts",), ("created_at",))
        or _first_extracted(
            payload,
            ("activated_at",),
            ("activation_ts",),
            ("timestamp",),
            ("ts",),
            ("created_at",),
        )
    )
    if activated_at is None:
        return None

    snapshot = _snapshot_from_historical_payload(record, payload)
    if snapshot is None:
        return None
    return _HistoricalConfigRecord(activated_at=int(activated_at), snapshot=snapshot)


def _snapshot_from_historical_payload(record: Any, payload: Mapping[str, Any]) -> ReplayConfigSnapshot | None:
    config_version = (
        _first_extracted(payload, ("config_version",), ("version",))
        or _first_extracted(record, ("config_version",), ("version",), ("id",), ("run_id",))
        or "historical"
    )
    try:
        return ReplayConfigSnapshot(
            config_version=str(config_version),
            config_source=CONFIG_SOURCE_HISTORICAL,
            entry_z_threshold=float(
                _required_config_number(
                    payload,
                    ("entry_z_threshold",),
                    ("entry_z",),
                    ("signals", "entry_z"),
                )
            ),
            exit_z_threshold=float(
                _required_config_number(
                    payload,
                    ("exit_z_threshold",),
                    ("exit_z",),
                    ("signals", "exit_z"),
                )
            ),
            persistence_candles=int(
                _required_config_number(
                    payload,
                    ("persistence_candles",),
                    ("min_persist_bars",),
                    ("signals", "min_persist_bars"),
                )
            ),
            max_hold_seconds=float(
                _required_config_number(
                    payload,
                    ("max_hold_seconds",),
                    ("exit", "max_hold_seconds"),
                    ("advanced_ml", "max_hold_seconds"),
                )
            ),
            min_zero_crossings=int(
                _required_config_number(
                    payload,
                    ("min_zero_crossings",),
                    ("zero_crossings_min",),
                    ("signals", "zero_crossings_min"),
                    ("strategy", "min_zero_crossings"),
                )
            ),
            min_liquidity_score=_optional_config_number(
                payload,
                ("min_liquidity_score",),
                ("exit", "min_liquidity_score"),
            ),
            max_orderbook_age_ms=_optional_config_number(
                payload,
                ("max_orderbook_age_ms",),
                ("max_book_age_ms",),
                ("advanced_ml", "max_book_age_ms"),
                ("microstructure", "max_book_age_ms"),
            ),
            max_spread_bps=_optional_config_number(
                payload,
                ("max_spread_bps",),
                ("wide_spread_bps",),
                ("advanced_ml", "wide_spread_bps"),
                ("microstructure", "wide_spread_bps"),
            ),
            max_slippage_bps=_optional_config_number(
                payload,
                ("max_slippage_bps",),
                ("max_allowed_slippage_bps",),
                ("microstructure", "max_allowed_slippage_bps"),
            ),
            hedge_ratio_sizing_enabled=(
                _optional_config_bool(
                    payload,
                    ("hedge_ratio_sizing_enabled",),
                    ("hedge_sizing", "enabled"),
                    ("hedge_ratio", "sizing_enabled"),
                    ("strategy", "hedge_ratio_sizing_enabled"),
                )
                or False
            ),
            hedge_sizing_mode=(
                _optional_config_text(
                    payload,
                    ("hedge_sizing_mode",),
                    ("hedge_sizing", "mode"),
                    ("hedge_ratio", "sizing_mode"),
                    ("strategy", "hedge_sizing_mode"),
                )
                or "equal_notional"
            ),
            min_hedge_ratio=(
                _optional_config_number(
                    payload,
                    ("min_hedge_ratio",),
                    ("hedge_ratio", "min"),
                    ("strategy", "min_hedge_ratio"),
                )
                or 0.20
            ),
            max_hedge_ratio=(
                _optional_config_number(
                    payload,
                    ("max_hedge_ratio",),
                    ("hedge_ratio", "max"),
                    ("strategy", "max_hedge_ratio"),
                )
                or 5.00
            ),
            reject_negative_hedge_ratio=(
                True
                if _optional_config_bool(
                    payload,
                    ("reject_negative_hedge_ratio",),
                    ("hedge_ratio", "reject_negative"),
                    ("strategy", "reject_negative_hedge_ratio"),
                )
                is None
                else bool(
                    _optional_config_bool(
                        payload,
                        ("reject_negative_hedge_ratio",),
                        ("hedge_ratio", "reject_negative"),
                        ("strategy", "reject_negative_hedge_ratio"),
                    )
                )
            ),
            max_hedge_sizing_error_pct=(
                _optional_config_number(
                    payload,
                    ("max_hedge_sizing_error_pct",),
                    ("hedge_sizing", "max_error_pct"),
                    ("strategy", "max_hedge_sizing_error_pct"),
                )
                or 0.10
            ),
            max_hedge_ratio_drift_pct=(
                _optional_config_number(
                    payload,
                    ("max_hedge_ratio_drift_pct",),
                    ("hedge_ratio", "max_drift_pct"),
                    ("strategy", "max_hedge_ratio_drift_pct"),
                )
                or 0.20
            ),
            severe_hedge_ratio_drift_pct=(
                _optional_config_number(
                    payload,
                    ("severe_hedge_ratio_drift_pct",),
                    ("hedge_ratio", "severe_drift_pct"),
                    ("strategy", "severe_hedge_ratio_drift_pct"),
                )
                or 0.35
            ),
            min_cointegration_window=int(
                _optional_config_number(
                    payload,
                    ("min_cointegration_window",),
                    ("cointegration", "min_window"),
                    ("strategy", "min_cointegration_window"),
                )
                or 120
            ),
        )
    except (TypeError, ValueError):
        return None


def _record_payload(record: Any) -> Mapping[str, Any]:
    for key in ("config_values", "config_snapshot", "config_snapshot_json", "config", "snapshot"):
        value = _extract_value(record, (key,))
        if isinstance(value, Mapping):
            return value
    if isinstance(record, Mapping):
        return record
    return {}


def _load_historical_config_records(historical_log_path: str | Path | None) -> list[Any]:
    paths = [Path(historical_log_path)] if historical_log_path is not None else list(DEFAULT_CONFIG_VERSION_LOG_PATHS)
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        records = _read_config_log(path)
        if records:
            return records
    return []


def _read_config_log(path: Path) -> list[Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    if not text.strip():
        return []

    if path.suffix.lower() == ".jsonl":
        records: list[Any] = []
        for line in text.splitlines():
            raw = line.strip()
            if not raw:
                continue
            try:
                records.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
        return records

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, Mapping):
        for key in ("configs", "versions", "records", "events", "history"):
            value = parsed.get(key)
            if isinstance(value, list):
                return value
    return []


def _current_max_hold_seconds(current_config: Any, env: Mapping[str, str]) -> float:
    explicit = _find_number(
        current_config,
        ("max_hold_seconds",),
        ("exit", "max_hold_seconds"),
        ("advanced_ml", "max_hold_seconds"),
    )
    if explicit is not None:
        return float(explicit)

    raw_seconds = _first_env_value(env, "STATBOT_ADVANCED_ML_MAX_HOLD_SECONDS", "STATBOT_MAX_HOLD_SECONDS")
    parsed_seconds = _parse_float(raw_seconds)
    if parsed_seconds is not None:
        return parsed_seconds

    raw_hours = _first_env_value(env, "STATBOT_ATM_MR_MAX_HOLD_HOURS")
    parsed_hours = _parse_float(raw_hours)
    if parsed_hours is not None:
        return parsed_hours * 3600.0
    return 6.0 * 3600.0


def _number_from_config_or_env(
    current_config: Any,
    env: Mapping[str, str],
    *,
    aliases: tuple[tuple[str, ...], ...],
    env_names: tuple[str, ...],
    default: float,
) -> float:
    config_value = _find_number(current_config, *aliases)
    if config_value is not None:
        return config_value
    env_value = _parse_float(_first_env_value(env, *env_names))
    if env_value is not None:
        return env_value
    return default


def _optional_number_from_config_or_env(
    current_config: Any,
    env: Mapping[str, str],
    *,
    aliases: tuple[tuple[str, ...], ...],
    env_names: tuple[str, ...],
    default: float | None,
) -> float | None:
    config_value = _find_number(current_config, *aliases)
    if config_value is not None:
        return config_value
    env_value = _parse_float(_first_env_value(env, *env_names))
    if env_value is not None:
        return env_value
    return default


def _bool_from_config_or_env(
    current_config: Any,
    env: Mapping[str, str],
    *,
    aliases: tuple[tuple[str, ...], ...],
    env_names: tuple[str, ...],
    default: bool,
) -> bool:
    config_value = _find_bool(current_config, *aliases)
    if config_value is not None:
        return config_value
    env_value = _parse_bool(_first_env_value(env, *env_names))
    if env_value is not None:
        return env_value
    return default


def _text_from_config_or_env(
    current_config: Any,
    env: Mapping[str, str],
    *,
    aliases: tuple[tuple[str, ...], ...],
    env_names: tuple[str, ...],
    default: str,
) -> str:
    config_value = _find_text(current_config, *aliases)
    if config_value is not None:
        return config_value
    env_value = _first_env_value(env, *env_names)
    if env_value is not None:
        return env_value
    return default


def _required_config_number(payload: Any, *paths: tuple[str, ...]) -> float:
    value = _find_number(payload, *paths)
    if value is None:
        raise ValueError("historical config record missing required replay field")
    return value


def _optional_config_number(payload: Any, *paths: tuple[str, ...]) -> float | None:
    return _find_number(payload, *paths)


def _optional_config_bool(payload: Any, *paths: tuple[str, ...]) -> bool | None:
    return _find_bool(payload, *paths)


def _optional_config_text(payload: Any, *paths: tuple[str, ...]) -> str | None:
    return _find_text(payload, *paths)


def _find_number(source: Any, *paths: tuple[str, ...]) -> float | None:
    for path in paths:
        value = _extract_value(source, path)
        parsed = _parse_float(value)
        if parsed is not None:
            return parsed
    return None


def _find_bool(source: Any, *paths: tuple[str, ...]) -> bool | None:
    for path in paths:
        value = _extract_value(source, path)
        parsed = _parse_bool(value)
        if parsed is not None:
            return parsed
    return None


def _find_text(source: Any, *paths: tuple[str, ...]) -> str | None:
    for path in paths:
        value = _extract_value(source, path)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _extract_value(source: Any, path: tuple[str, ...]) -> Any:
    current = source
    for key in path:
        if current is None:
            return None
        if isinstance(current, Mapping):
            current = current.get(key)
        elif hasattr(current, key):
            current = getattr(current, key)
        else:
            return None
    return current


def _first_extracted(source: Any, *paths: tuple[str, ...]) -> Any:
    for path in paths:
        value = _extract_value(source, path)
        if value is not None:
            return value
    return None


def _first_env_value(env: Mapping[str, str], *names: str) -> str | None:
    for name in names:
        raw = env.get(name)
        if raw is not None and str(raw).strip() != "":
            return str(raw).strip()
    return None


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if not text:
        return None
    if text in {"1", "true", "yes", "y", "on", "enabled"}:
        return True
    if text in {"0", "false", "no", "n", "off", "disabled"}:
        return False
    return None


def _required_timestamp(value: Any) -> int:
    timestamp = _coerce_timestamp(value)
    if timestamp is None:
        raise ValueError("config_at requires a valid timestamp")
    return int(timestamp)


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


__all__ = [
    "CONFIG_SOURCE_CURRENT_APPROXIMATE",
    "CONFIG_SOURCE_HISTORICAL",
    "CURRENT_CONFIG_WARNING",
    "config_at",
    "current_config_snapshot",
]
