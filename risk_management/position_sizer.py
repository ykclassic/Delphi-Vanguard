import logging


class PositionSizer:
    def __init__(self, config):
        self.config = config
        self.risk_pct = config.get('risk_per_trade_percent', 1.0)
        self.max_spread_cost_pct = 0.15

    def calculate(self, df, symbol, signal_type):
        last_price = df['Close'].iloc[-1]
        atr = df['ATR'].iloc[-1]
        if "BUY" in signal_type:
            sl = last_price - (atr * self.config.get('default_stop_loss_atr', 1.5))
            tp = last_price + (atr * self.config.get('default_take_profit_ratio', 2.0))
        else:
            sl = last_price + (atr * self.config.get('default_stop_loss_atr', 1.5))
            tp = last_price - (atr * self.config.get('default_take_profit_ratio', 2.0))
        estimated_spread = self._estimate_spread(symbol)
        potential_profit = abs(tp - last_price)
        if potential_profit <= 0 or (estimated_spread / potential_profit) > self.max_spread_cost_pct:
            logging.warning(f"QUALITY ALERT: Spread on {symbol} is too high for this target. Aborting.")
            return None
        return {"entry": round(last_price, 5), "sl": round(sl, 5), "tp": round(tp, 5)}

    def _estimate_spread(self, symbol):
        spreads = {"EURUSD": 0.00012, "GBPUSD": 0.00018, "USDJPY": 0.012, "EURJPY": 0.018, "GBPJPY": 0.025, "XAUUSD": 0.35}
        return spreads.get(symbol, 0.0002)
