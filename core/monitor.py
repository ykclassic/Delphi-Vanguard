import pandas as pd
import logging
from core.data_ingestion import DataManager


class SignalMonitor:
    def __init__(self, config):
        self.config = config
        self.log_path = "logs/trade_log.csv"
        self.data_manager = DataManager(config)

    def check_outcomes(self):
        """Evaluates the Oracle baseline's hypothetical outcomes.

        This is research/forward-test bookkeeping, not broker reconciliation.
        """
        try:
            df_logs = pd.read_csv(self.log_path)
        except FileNotFoundError:
            return []

        if 'Outcome' not in df_logs.columns:
            df_logs['Outcome'] = 'Pending'
        df_logs['Outcome'] = df_logs['Outcome'].fillna('Pending')

        updates = []
        for idx, row in df_logs.iterrows():
            if (row['Outcome'] != 'Pending' or pd.isna(row['Signal']) or
                    str(row['Signal']).strip() == 'None' or row['Entry'] == 0.0):
                continue

            symbol = row['Symbol']
            trade_time = pd.to_datetime(row['Timestamp'])
            data = self.data_manager.get_latest_data(symbol)
            if data is None or data.empty:
                continue

            time_column = next((c for c in ('Datetime', 'Date') if c in data.columns), None)
            if time_column is None:
                logging.warning("No candle timestamp column for %s", symbol)
                continue
            timestamps = pd.to_datetime(data[time_column], utc=True, errors='coerce')
            trade_time = pd.Timestamp(trade_time, tz='UTC') if pd.Timestamp(trade_time).tzinfo is None else pd.Timestamp(trade_time).tz_convert('UTC')
            future_data = data.loc[timestamps > trade_time].copy()
            if future_data.empty:
                continue

            outcome = "Pending"
            trigger_price = future_data['Close'].iloc[-1]
            for _, candle in future_data.iterrows():
                high, low = candle['High'], candle['Low']
                if "BUY" in str(row['Signal']):
                    if low <= row['SL']:
                        outcome, trigger_price = "❌ STOP LOSS", row['SL']
                        break
                    if high >= row['TP']:
                        outcome, trigger_price = "✅ TAKE PROFIT", row['TP']
                        break
                elif "SELL" in str(row['Signal']):
                    if high >= row['SL']:
                        outcome, trigger_price = "❌ STOP LOSS", row['SL']
                        break
                    if low <= row['TP']:
                        outcome, trigger_price = "✅ TAKE PROFIT", row['TP']
                        break

            if outcome != "Pending":
                df_logs.at[idx, 'Outcome'] = outcome
                updates.append(f"**{symbol}**: {outcome} at price {trigger_price:.5f}")

        df_logs.to_csv(self.log_path, index=False)
        return updates
