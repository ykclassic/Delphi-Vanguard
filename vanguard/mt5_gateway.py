"""Isolated MT5 execution gateway. Live order authority lives here only."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from vanguard.interfaces import AccountSnapshot, ExecutionMode, OrderRequest, OrderResult, Quote, Side
from vanguard.market_data import validate_quote


class MT5Gateway:
    def __init__(self, mt5: Any, mode: ExecutionMode = ExecutionMode.DEMO, max_quote_age_seconds: float = 5.0) -> None:
        if mode is ExecutionMode.LIVE:
            raise ValueError("LIVE mode is intentionally disabled until demo validation is complete")
        self.mt5 = mt5
        self.mode = mode
        self.max_quote_age_seconds = max_quote_age_seconds

    def account(self) -> AccountSnapshot:
        info = self.mt5.account_info()
        if info is None:
            raise RuntimeError(f"MT5 account_info unavailable: {getattr(self.mt5, 'last_error', lambda: '')()}")
        if hasattr(info, "trade_allowed") and not info.trade_allowed:
            raise RuntimeError("MT5 account does not allow trading")
        return AccountSnapshot(float(info.equity), float(info.balance), float(info.margin), float(info.margin_free), str(info.currency), datetime.now(timezone.utc))

    def quote(self, symbol: str) -> Quote:
        info = self.mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"MT5 symbol unavailable: {symbol}")
        if not info.visible and not self.mt5.symbol_select(symbol, True):
            raise RuntimeError(f"MT5 could not select symbol: {symbol}")
        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(f"MT5 tick unavailable: {symbol}")
        return Quote(symbol, float(tick.bid), float(tick.ask), "MT5", datetime.fromtimestamp(tick.time, tz=timezone.utc), str(getattr(tick, "time_msc", tick.time)))

    def submit(self, request: OrderRequest) -> OrderResult:
        if self.mode is ExecutionMode.LIVE:
            raise RuntimeError("live execution disabled")
        quote = self.quote(request.symbol)
        validate_quote(quote, max_age_seconds=self.max_quote_age_seconds)
        account = self.account()
        if account.free_margin <= 0:
            raise RuntimeError("insufficient free margin")
        order_type = self.mt5.ORDER_TYPE_BUY if request.side is Side.BUY else self.mt5.ORDER_TYPE_SELL
        price = quote.executable_price(request.side)
        payload = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": request.symbol,
            "volume": request.volume,
            "type": order_type,
            "price": price,
            "sl": request.stop_loss,
            "tp": request.take_profit,
            "deviation": 10,
            "magic": 260902,
            "comment": f"Vanguard:{request.client_order_id}",
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": getattr(self.mt5, "ORDER_FILLING_RETURN", getattr(self.mt5, "ORDER_FILLING_IOC", 1)),
        }
        check = self.mt5.order_check(payload)
        if check is None or getattr(check, "retcode", 0) != 0:
            code = getattr(check, "retcode", "NO_RESULT")
            return OrderResult(request.client_order_id, None, False, False, None, f"MT5 order_check rejected: {code}", datetime.now(timezone.utc))
        result = self.mt5.order_send(payload)
        now = datetime.now(timezone.utc)
        if result is None:
            return OrderResult(request.client_order_id, None, False, False, None, "MT5 order_send returned None", now)
        done = getattr(self.mt5, "TRADE_RETCODE_DONE", 10009)
        accepted = getattr(result, "retcode", 0) == done
        return OrderResult(request.client_order_id, str(getattr(result, "order", "")) or None, accepted, accepted, float(getattr(result, "price", price)) if accepted else None, str(getattr(result, "comment", "")), now)
