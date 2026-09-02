import os
import yaml
import logging
import datetime
import pandas as pd
from core.data_ingestion import DataManager
from core.regime_detector import RegimeDetector
from core.logger import PerformanceLogger
from core.session_manager import SessionManager
from risk_management.news_sentry import NewsSentry
from risk_management.position_sizer import PositionSizer
from strategies.trend_following import TrendStrategy
from execution.discord_adapter import DiscordNotifier


def load_config():
    with open("config/settings.yaml", "r") as f:
        config = yaml.safe_load(f)
    webhook_env = os.getenv("DISCORD_WEBHOOK_URL")
    if webhook_env:
        config['discord']['webhook_url'] = webhook_env
    return config


def run_bot():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.info("--- Delphi Vanguard baseline: Quality Engine Starting ---")
    config = load_config()
    if not config['discord'].get('webhook_url'):
        logging.error("Missing DISCORD_WEBHOOK_URL. Bot cannot send alerts.")
        return

    data_manager = DataManager(config)
    regime_detector = RegimeDetector()
    perf_logger = PerformanceLogger()
    news_sentry = NewsSentry(config)
    session_manager = SessionManager()
    strategy = TrendStrategy(config)
    position_sizer = PositionSizer(config)
    notifier = DiscordNotifier(config)
    summary_results = []
    current_session = session_manager.get_current_session()

    for symbol in config['symbols']:
        logging.info(f"Analyzing {symbol}...")
        if news_sentry.is_market_volatile(symbol):
            logging.warning(f"Skipping {symbol}: High-impact news detected.")
            summary_results.append(f"⚪ {symbol}: News Sentry Block")
            continue
        df = data_manager.get_latest_data(symbol)
        if df is None or len(df) < 50:
            logging.warning(f"Insufficient data for {symbol}.")
            summary_results.append(f"🔴 {symbol}: Data Fetch Error")
            continue
        regime = regime_detector.classify(df)
        regime_map = {0: "🟦 Range", 1: "🟩 Trend", 2: "🟧 Chaos"}
        logging.info(f"{symbol} detected in {regime_map.get(regime)} regime.")
        signal_type = strategy.generate_signal(df, regime)
        if signal_type:
            risk_data = position_sizer.calculate(df, symbol, signal_type)
            if risk_data:
                notifier.send_signal(symbol, signal_type, risk_data, current_session)
                perf_logger.log_scan(symbol, regime, signal_type, risk_data)
                summary_results.append(f"🔥 {symbol}: {signal_type} SENT")
                logging.info(f"Signal confirmed and sent for {symbol}.")
            else:
                summary_results.append(f"🚫 {symbol}: Rejected (Low Quality/High Spread)")
                logging.warning(f"Signal rejected for {symbol} due to poor Risk/Reward (Spread).")
        else:
            summary_results.append(f"{regime_map.get(regime)} {symbol}: Scanning...")

    notifier.send_heartbeat(summary_results, current_session)
    now = datetime.datetime.now(datetime.timezone.utc)
    if now.weekday() == 4 and now.hour == 21:
        generate_weekly_report(perf_logger, notifier)
    logging.info("--- Scan Cycle Complete ---")


def generate_weekly_report(logger, notifier):
    try:
        df = pd.read_csv(logger.file_path)
        total_signals = len(df[df['Signal'] != 'None'])
        wins = len(df[df['Outcome'] == '✅ TAKE PROFIT'])
        losses = len(df[df['Outcome'] == '❌ STOP LOSS'])
        report = [f"**Total Signals:** {total_signals}", f"**Wins:** {wins} ✅", f"**Losses:** {losses} ❌", f"**Win Rate:** {(wins/max(1, wins+losses))*100:.1f}%"]
        notifier.send_heartbeat(report, "WEEKLY PERFORMANCE SUMMARY 📊")
    except Exception as exc:
        logging.error(f"Report generation failed: {exc}")


if __name__ == "__main__":
    run_bot()
