"""Strategy B: short-term mean reversion (Connors RSI(2) style), long only."""

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
    }
    param_grid = {
        "entry_rsi": [5.0, 10.0, 20.0],
        "exit_len": [3, 5, 10],
    }
    max_bars = 10

    def signals(self, bars: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        close = bars["close"]
        false = pd.Series(False, index=bars.index)
        return pd.DataFrame({
            "long_entry": (close > sma(close, p["trend_len"])) & (rsi(close, p["rsi_len"]) < p["entry_rsi"]),
            "short_entry": false,
            "long_exit": close > sma(close, p["exit_len"]),
            "short_exit": false,
            "stop_dist": p["stop_atr"] * atr(bars, p["atr_len"]),
            "target_dist": np.nan,
        }, index=bars.index)
