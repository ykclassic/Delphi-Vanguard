"""Broker-authoritative quote access. No Yahoo or synthetic live quote fallback."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from vanguard.interfaces import Quote


class MarketDataError(RuntimeError):
    pass


class StaleQuote(MarketDataError):
    pass


class MT5MarketData:
    """Reads quotes from the connected MT5 terminal and validates freshness."""

    def __init__(self, mt5: Any, max_age_seconds: float = 5.0) -> None:
        self.mt5 = mt5
        self.max_age = timedelta(seconds=max_age_seconds)

    def quote(self, symbol: str) -> Quote:
        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None:
            raise MarketDataError(f"no MT5 tick for {symbol}")
        ts = getattr(tick, "time", 0)
        timestamp = datetime.fromtimestamp(ts, tz=timezone.utc)
        now = datetime.now(timezone.utc)
        if now - timestamp > self.max_age:
            raise StaleQuote(f"stale quote for {symbol}: {timestamp.isoformat()}")
        return Quote(symbol=symbol, bid=float(tick.bid), ask=float(tick.ask), provider="MT5", timestamp=timestamp, sequence=str(getattr(tick, "time_msc", ts)))


class PaperMarketData:
    """Deterministic quote source used only for paper validation tests."""

    def __init__(self, quotes: dict[str, Quote]) -> None:
        self.quotes = dict(quotes)

    def quote(self, symbol: str) -> Quote:
        try:
            return self.quotes[symbol]
        except KeyError as exc:
            raise MarketDataError(f"paper quote unavailable for {symbol}") from exc


def validate_quote(quote: Quote, now: datetime | None = None, max_age_seconds: float = 5.0) -> None:
    now = now or datetime.now(timezone.utc)
    if quote.timestamp.tzinfo is None:
        raise MarketDataError("quote timestamp must be timezone-aware")
    age = (now - quote.timestamp).total_seconds()
    if age < -2:
        raise MarketDataError("quote timestamp is ahead of local clock")
    if age > max_age_seconds:
        raise StaleQuote(f"quote age {age:.3f}s exceeds {max_age_seconds}s")
