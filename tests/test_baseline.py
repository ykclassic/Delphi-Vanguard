import pandas as pd

from risk_management.position_sizer import PositionSizer
from strategies.trend_following import TrendStrategy


def _config():
    return {
        "risk_per_trade_percent": 1.0,
        "default_stop_loss_atr": 1.5,
        "default_take_profit_ratio": 2.0,
    }


def test_position_sizer_returns_valid_baseline_levels():
    df = pd.DataFrame({"Close": [1.1000], "ATR": [0.0010]})
    result = PositionSizer(_config()).calculate(df, "EURUSD", "BUY (Trend)")
    assert result is not None
    assert result["sl"] < result["entry"] < result["tp"]


def test_trend_strategy_contract_returns_none_or_signal():
    close = pd.Series([1.0 + i * 0.001 for i in range(100)])
    df = pd.DataFrame({"Close": close, "High": close + 0.001, "Low": close - 0.001})
    signal = TrendStrategy({}).generate_signal(df, regime=1)
    assert signal in {None, "BUY (Trend)", "SELL (Trend)"}
