"""Adapter protocols for integrating advanced ML modules with the existing bot.

This file intentionally defines contracts only. Concrete adapters should live in
separate modules and translate these methods to the current repository APIs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, TypeAlias, runtime_checkable


PairIdentity: TypeAlias = Any
OrderBookSnapshot: TypeAlias = Any


class PairState(str, Enum):
    ELITE = "elite"
    STABLE = "stable"
    WARNING = "warning"
    HOSPITAL = "hospital"
    GRAVEYARD = "graveyard"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class BotAdapterSpec:
    pair_state_source: str
    orderbook_cache_source: str
    trade_manager_source: str
    trade_lifecycle_hooks: list[str]
    supports_async_execution: bool
    supports_position_reconciliation: bool


@runtime_checkable
class ExistingBotAdapter(Protocol):
    def get_pair_state(self, pair: PairIdentity) -> PairState:
        ...

    def get_orderbook_snapshot(self, symbol: str) -> OrderBookSnapshot | None:
        ...

    def get_current_position(self, pair: PairIdentity) -> dict[str, Any] | None:
        ...

    def get_trade_lifecycle_event(self) -> dict[str, Any] | None:
        ...

    def read_existing_trade_state(self) -> dict[str, Any] | None:
        ...

    def submit_exit_order(
        self,
        pair: PairIdentity,
        exit_percentage: float,
        order_style: str,
        reason: str,
    ) -> dict[str, Any]:
        ...


__all__ = [
    "BotAdapterSpec",
    "ExistingBotAdapter",
    "PairState",
]
