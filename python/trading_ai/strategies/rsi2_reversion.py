"""Strategy B: short-term mean reversion (Connors RSI(2) style). Long only by
default; RSI2Both mirrors the rules for shorts in downtrends."""

from __future__ import annotations

import numpy as np
import pandas as pd

from trading_ai.indicators import atr, rsi, sma
from trading_ai.strategies.base import Strategy


class RSI2Reversion(Strategy):
    name = "rsi2_reversion"
    description = "In an uptrend (close > SMA200) buy when RSI(2) is deeply oversold; exit when close > SMA(5)."
    default_params = {
        "rsi_len": 2,
        "entry_rsi": 10.0,
        "trend_len": 200,
        "exit_len": 5,
        "atr_len": 10,
        "stop_atr": 3.0,   # prop firms require a stop; kept wide so it rarely interferes
        "allow_short": False,
    }
    param_grid = {
        "entry_rsi": [5.0, 10.0, 20.0],
        "exit_len": [3, 5, 10],
    }
    max_bars = 10
    # US indices: strongest published evidence and the best walk-forward results.
    # Other indices were tested (2026-09-26) and were flat or negative.
    default_symbols = ("SPX500", "NAS100", "DOW30")

    def signals(self, bars: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        close = bars["close"]
        trend = sma(close, p["trend_len"])
        r = rsi(close, p["rsi_len"])
        exit_ma = sma(close, p["exit_len"])
        shorts = bool(p["allow_short"])
        return pd.DataFrame({
            "long_entry": (close > trend) & (r < p["entry_rsi"]),
            "short_entry": (close < trend) & (r > 100 - p["entry_rsi"]) & shorts,
            "long_exit": close > exit_ma,
            "short_exit": close < exit_ma,
            "stop_dist": p["stop_atr"] * atr(bars, p["atr_len"]),
            "target_dist": np.nan,
        }, index=bars.index)


class RSI2Both(RSI2Reversion):
    name = "rsi2_both"
    description = "RSI(2) mean reversion both ways: buy dips in uptrends, sell rallies in downtrends."
    default_params = RSI2Reversion.default_params | {"allow_short": True}
    default_symbols = ("GOLD", "EURUSD", "GBPUSD", "USDJPY")
