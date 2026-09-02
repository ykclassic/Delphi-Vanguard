"""Stable domain contracts for the Vanguard reliability pipeline."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Mapping, Protocol


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class ExecutionMode(str, Enum):
    PAPER = "PAPER"
    DEMO = "DEMO"
    LIVE = "LIVE"


@dataclass(frozen=True)
class Quote:
    symbol: str
    bid: float
    ask: float
    provider: str
    timestamp: datetime
    sequence: str | None = None

    def __post_init__(self) -> None:
        if self.bid <= 0 or self.ask <= 0 or self.ask < self.bid:
            raise ValueError("quote must have positive bid/ask with ask >= bid")
        if self.timestamp.tzinfo is None:
            raise ValueError("quote timestamp must be timezone-aware")

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    def executable_price(self, side: Side) -> float:
        return self.ask if side is Side.BUY else self.bid


@dataclass(frozen=True)
class AccountSnapshot:
    equity: float
    balance: float
    margin: float
    free_margin: float
    currency: str
    timestamp: datetime


@dataclass(frozen=True)
class SignalProposal:
    signal_id: str
    symbol: str
    side: Side
    strategy_id: str
    strategy_version: str
    created_at: datetime
    expires_at: datetime
    reference_price: float
    stop_loss: float
    take_profit: float
    confidence: float
    rationale: str
    features: Mapping[str, float]


@dataclass(frozen=True)
class RiskContext:
    open_positions: int
    daily_loss_percent: float
    drawdown_percent: float
    value_per_price_unit: float

    def __post_init__(self) -> None:
        if self.open_positions < 0:
            raise ValueError("open_positions cannot be negative")
        if self.daily_loss_percent < 0 or self.drawdown_percent < 0:
            raise ValueError("loss and drawdown percentages cannot be negative")
        if self.value_per_price_unit <= 0:
            raise ValueError("value_per_price_unit must be positive")


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason_codes: tuple[str, ...]
    volume: float
    risk_amount: float
    stop_distance: float
    reward_distance: float
    risk_reward: float
    quote_timestamp: datetime
    context: RiskContext


@dataclass(frozen=True)
class OrderRequest:
    client_order_id: str
    signal_id: str
    symbol: str
    side: Side
    volume: float
    stop_loss: float
    take_profit: float
    mode: ExecutionMode


@dataclass(frozen=True)
class OrderResult:
    client_order_id: str
    broker_order_id: str | None
    accepted: bool
    filled: bool
    fill_price: float | None
    message: str
    timestamp: datetime


class MarketDataProvider(Protocol):
    def quote(self, symbol: str) -> Quote: ...


class BrokerGateway(Protocol):
    def account(self) -> AccountSnapshot: ...
    def quote(self, symbol: str) -> Quote: ...
    def submit(self, request: OrderRequest) -> OrderResult: ...


class Ledger(Protocol):
    def append(self, event_type: str, aggregate_id: str, payload: Mapping[str, object]) -> str: ...


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
