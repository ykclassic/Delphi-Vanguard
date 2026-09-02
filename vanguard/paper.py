"""Deterministic paper broker for end-to-end safety validation."""
from __future__ import annotations

from datetime import datetime, timezone

from vanguard.interfaces import AccountSnapshot, ExecutionMode, OrderRequest, OrderResult, Quote
from vanguard.market_data import PaperMarketData


class PaperBroker:
    mode = ExecutionMode.PAPER

    def __init__(self, market_data: PaperMarketData, equity: float = 10_000.0) -> None:
        self.market_data = market_data
        self.equity = equity
        self.orders: dict[str, OrderResult] = {}

    def account(self) -> AccountSnapshot:
        now = datetime.now(timezone.utc)
        return AccountSnapshot(self.equity, self.equity, 0.0, self.equity, "USD", now)

    def quote(self, symbol: str) -> Quote:
        return self.market_data.quote(symbol)

    def lookup_order(self, client_order_id: str) -> OrderResult | None:
        return self.orders.get(client_order_id)

    def submit(self, request: OrderRequest) -> OrderResult:
        if request.mode is not ExecutionMode.PAPER:
            raise ValueError("PaperBroker accepts PAPER execution mode only")
        existing = self.orders.get(request.client_order_id)
        if existing is not None:
            return existing
        quote = self.quote(request.symbol)
        price = quote.executable_price(request.side)
        result = OrderResult(request.client_order_id, f"PAPER-{request.client_order_id}", True, True, price, "paper fill", datetime.now(timezone.utc))
        self.orders[request.client_order_id] = result
        return result
