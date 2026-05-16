"""Tests for replay marker field name correctness in _add_replay_trade_markers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services import cointegrated_pairs as cp


def _ts(minute: int) -> datetime:
    return datetime(2026, 5, 1, 0, minute, tzinfo=timezone.utc)


def _make_point(zscore: float | None, minute: int) -> dict:
    """Minimal chart point with required keys."""
    return {
        "ts": _ts(minute),
        "zscore": zscore,
        "replay_entry_z": None,
        "replay_entry_label": None,
        "replay_entry_count": 0,
        "replay_entry_side": None,
        "replay_buy_entry_z": None,
        "replay_buy_entry_label": None,
        "replay_buy_entry_count": 0,
        "replay_sell_entry_z": None,
        "replay_sell_entry_label": None,
        "replay_sell_entry_count": 0,
        "replay_exit_z": None,
        "replay_exit_label": None,
        "replay_exit_count": 0,
        "replay_exit_candidate_z": None,
        "replay_exit_candidate_label": None,
        "replay_exit_candidate_count": 0,
    }


def _build_buy_spread_sequence(monkeypatch) -> list[dict]:
    """
    Build a point sequence that triggers a BUY_SPREAD entry then an exit.

    Default settings: entry_z=2.0, entry_z_max=3.0, exit_z=0.35, min_persist=4,
    min_qualified=3, clean_bars=2, tolerance=0.05 => entry_floor~=1.95.

    BUY_SPREAD requires z <= -entry_floor (i.e. <= -1.95) for min_persist bars.
    Exit requires abs(z) <= 0.35.
    """
    monkeypatch.setenv("STATBOT_MIN_PERSIST_BARS", "4")
    monkeypatch.setenv("STATBOT_ENTRY_MIN_QUALIFIED_BARS", "3")
    monkeypatch.setenv("STATBOT_ENTRY_EXTREME_CLEAN_BARS", "2")
    monkeypatch.setenv("STATBOT_ENTRY_Z", "2.0")
    monkeypatch.setenv("STATBOT_ENTRY_Z_MAX", "3.0")
    monkeypatch.setenv("STATBOT_EXIT_Z", "0.35")
    monkeypatch.setenv("STATBOT_ENTRY_Z_TOLERANCE", "0.05")
    monkeypatch.setenv("STATBOT_ENTRY_MIN_CONTINUOUS_SECONDS", "0")

    points = []
    # Bars 0-3: z deeply negative to satisfy BUY_SPREAD persistence (min_persist=4)
    for i in range(4):
        points.append(_make_point(-2.5, i))
    # Bar 4: still negative — the entry marker should appear here (history length == min_persist by bar 3,
    # but bar 3 is the 4th item so history[0..3] covers bars 0-3; bar 4 then satisfies the loop at idx=4)
    points.append(_make_point(-2.5, 4))
    # Bars 5-6: remain in position (z still negative, no exit)
    points.append(_make_point(-2.2, 5))
    points.append(_make_point(-2.1, 6))
    # Bar 7: z near zero => exit
    points.append(_make_point(0.1, 7))
    return points


def _build_sell_spread_sequence(monkeypatch) -> list[dict]:
    """
    Build a point sequence that triggers a SELL_SPREAD entry.
    SELL_SPREAD requires z >= entry_floor (i.e. >= 1.95).
    """
    # env vars already set by _build_buy_spread_sequence if called together,
    # but this function is self-contained.
    monkeypatch.setenv("STATBOT_MIN_PERSIST_BARS", "4")
    monkeypatch.setenv("STATBOT_ENTRY_MIN_QUALIFIED_BARS", "3")
    monkeypatch.setenv("STATBOT_ENTRY_EXTREME_CLEAN_BARS", "2")
    monkeypatch.setenv("STATBOT_ENTRY_Z", "2.0")
    monkeypatch.setenv("STATBOT_ENTRY_Z_MAX", "3.0")
    monkeypatch.setenv("STATBOT_EXIT_Z", "0.35")
    monkeypatch.setenv("STATBOT_ENTRY_Z_TOLERANCE", "0.05")
    monkeypatch.setenv("STATBOT_ENTRY_MIN_CONTINUOUS_SECONDS", "0")

    points = []
    for i in range(5):
        points.append(_make_point(2.5, i))
    return points


def test_buy_spread_entry_uses_new_field_names(monkeypatch):
    """BUY_SPREAD entry populates replay_buy_entry_z (new) and replay_entry_z (compat)."""
    points = _build_buy_spread_sequence(monkeypatch)
    stats = cp._add_replay_trade_markers(points)

    assert stats["replay_entries"] >= 1, "Expected at least one replay entry"

    buy_entry_points = [p for p in points if p.get("replay_buy_entry_z") is not None]
    assert buy_entry_points, "replay_buy_entry_z must be set on at least one point"

    compat_points = [p for p in points if p.get("replay_entry_z") is not None]
    assert compat_points, "replay_entry_z (backward compat) must also be set"


def test_buy_spread_exit_uses_new_field_names(monkeypatch):
    """Exit from a BUY_SPREAD position populates replay_exit_candidate_z (new) and replay_exit_z (compat)."""
    points = _build_buy_spread_sequence(monkeypatch)
    cp._add_replay_trade_markers(points)

    exit_candidate_points = [p for p in points if p.get("replay_exit_candidate_z") is not None]
    assert exit_candidate_points, "replay_exit_candidate_z must be set on exit point"

    exit_compat_points = [p for p in points if p.get("replay_exit_z") is not None]
    assert exit_compat_points, "replay_exit_z (backward compat) must also be set on exit point"


def test_sell_spread_entry_uses_new_field_names(monkeypatch):
    """SELL_SPREAD entry populates replay_sell_entry_z (new) and replay_entry_z (compat)."""
    points = _build_sell_spread_sequence(monkeypatch)
    stats = cp._add_replay_trade_markers(points)

    assert stats["replay_entries"] >= 1, "Expected at least one replay entry"

    sell_entry_points = [p for p in points if p.get("replay_sell_entry_z") is not None]
    assert sell_entry_points, "replay_sell_entry_z must be set on at least one point"

    compat_points = [p for p in points if p.get("replay_entry_z") is not None]
    assert compat_points, "replay_entry_z (backward compat) must also be set"


def test_buy_entry_does_not_set_sell_field(monkeypatch):
    """A BUY_SPREAD entry must not populate replay_sell_entry_z."""
    points = _build_buy_spread_sequence(monkeypatch)
    cp._add_replay_trade_markers(points)

    assert all(
        p.get("replay_sell_entry_z") is None for p in points
    ), "replay_sell_entry_z must remain None when only BUY_SPREAD entries occur"


def test_sell_entry_does_not_set_buy_field(monkeypatch):
    """A SELL_SPREAD entry must not populate replay_buy_entry_z."""
    points = _build_sell_spread_sequence(monkeypatch)
    cp._add_replay_trade_markers(points)

    assert all(
        p.get("replay_buy_entry_z") is None for p in points
    ), "replay_buy_entry_z must remain None when only SELL_SPREAD entries occur"
