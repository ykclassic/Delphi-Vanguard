import yfinance as yf
import pandas as pd
import logging
import time


class DataManager:
    def __init__(self, config):
        self.config = config
        self.timeframe = config.get('timeframe', '1h')
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

    def get_latest_data(self, symbol):
        """Fetches OHLCV data with retries.

        NOTE: This is retained only as the audited Oracle research baseline.
        It is not an authoritative live-trading data source.
        """
        ticker_str = f"{symbol}=X" if "=" not in symbol and symbol != "XAUUSD" else symbol
        if symbol == "XAUUSD":
            ticker_str = "GC=F"

        logging.info(f"Fetching data for {ticker_str}...")
        for attempt in range(3):
            try:
                ticker = yf.Ticker(ticker_str)
                data = ticker.history(period="1mo", interval=self.timeframe, raise_errors=True)
                if not data.empty:
                    return data.reset_index()
                logging.warning(f"Attempt {attempt + 1}: Received empty data for {symbol}")
            except Exception as exc:
                logging.error(f"Attempt {attempt + 1} failed for {symbol}: {exc}")
                time.sleep(2)
        return None
