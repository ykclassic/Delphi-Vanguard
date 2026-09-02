import pandas as pd
import datetime
import os


class PerformanceLogger:
    def __init__(self, file_path="logs/trade_log.csv"):
        self.file_path = file_path
        directory = os.path.dirname(self.file_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        if not os.path.exists(self.file_path):
            pd.DataFrame(columns=["Timestamp", "Symbol", "Regime", "Signal", "Entry", "SL", "TP", "Outcome"]).to_csv(self.file_path, index=False)

    def log_scan(self, symbol, regime, signal=None, risk_data=None):
        log_entry = {
            "Timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Symbol": symbol,
            "Regime": regime,
            "Signal": signal if signal else "None",
            "Entry": risk_data['entry'] if risk_data else 0.0,
            "SL": risk_data['sl'] if risk_data else 0.0,
            "TP": risk_data['tp'] if risk_data else 0.0,
            "Outcome": "Pending" if signal else "N/A"
        }
        pd.DataFrame([log_entry]).to_csv(self.file_path, mode='a', header=False, index=False)
