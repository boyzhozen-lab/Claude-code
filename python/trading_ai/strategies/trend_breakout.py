"""Strategy A: Donchian channel breakout, trend following."""

from __future__ import annotations

import numpy as np
import pandas as pd

from trading_ai.indicators import atr, prior_high, prior_low, sma
from trading_ai.strategies.base import Strategy


class TrendBreakout(Strategy):
    name = "trend_breakout"
    description = "Close above the N-bar high: go long; exit on the M-bar low. Mirror for shorts."
    default_params = {
        "entry_len": 55,
        "exit_len": 20,
        "atr_len": 20,
        "stop_atr": 2.0,
        "trend_filter": 200,   # only trade in the direction of this SMA; 0 disables
        "allow_short": True,
    }
    param_grid = {
        "entry_len": [20, 55, 100],
        "exit_len": [10, 20],
        "stop_atr": [2.0, 3.0],
    }
    default_symbols = ("GOLD", "NAS100", "SPX500", "DOW30", "EURUSD", "GBPUSD", "USDJPY")

    def signals(self, bars: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        close = bars["close"]
        up_ok = pd.Series(True, index=bars.index)
        down_ok = pd.Series(bool(p["allow_short"]), index=bars.index)
        if p["trend_filter"]:
            ma = sma(close, p["trend_filter"])
            up_ok &= close > ma
            down_ok &= close < ma
        return pd.DataFrame({
            "long_entry": (close > prior_high(bars, p["entry_len"])) & up_ok,
            "short_entry": (close < prior_low(bars, p["entry_len"])) & down_ok,
            "long_exit": close < prior_low(bars, p["exit_len"]),
            "short_exit": close > prior_high(bars, p["exit_len"]),
            "stop_dist": p["stop_atr"] * atr(bars, p["atr_len"]),
            "target_dist": np.nan,
        }, index=bars.index)
