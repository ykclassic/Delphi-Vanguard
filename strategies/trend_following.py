import ta
from strategies.base_strategy import BaseStrategy


class TrendStrategy(BaseStrategy):
    def generate_signal(self, df, regime):
        df['ema_fast'] = ta.trend.ema_indicator(df['Close'], window=20)
        df['ema_slow'] = ta.trend.ema_indicator(df['Close'], window=50)
        df['rsi'] = ta.momentum.rsi(df['Close'], window=14)
        bb = ta.volatility.BollingerBands(df['Close'], window=20)
        df['bb_upper'] = bb.bollinger_hband()
        df['bb_lower'] = bb.bollinger_lband()
        df['ATR'] = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)
        last_row, prev_row = df.iloc[-1], df.iloc[-2]
        if regime == 1:
            if prev_row['ema_fast'] <= prev_row['ema_slow'] and last_row['ema_fast'] > last_row['ema_slow'] and last_row['rsi'] > 50:
                return "BUY (Trend)"
            if prev_row['ema_fast'] >= prev_row['ema_slow'] and last_row['ema_fast'] < last_row['ema_slow'] and last_row['rsi'] < 50:
                return "SELL (Trend)"
        elif regime == 0:
            if last_row['Close'] <= last_row['bb_lower'] and last_row['rsi'] < 35:
                return "BUY (Mean Reversion)"
            if last_row['Close'] >= last_row['bb_upper'] and last_row['rsi'] > 65:
                return "SELL (Mean Reversion)"
        return None
