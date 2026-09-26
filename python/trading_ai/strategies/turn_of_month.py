"""Turn-of-the-month effect: stock indices have historically earned much of
their return in the last day(s) of a month and the first few of the next
(Ariel 1987; Lakonishok & Smidt 1988; McConnell & Xu 2008). Long only.

The trading calendar (which bar is the month's last) is taken from the bar
dates; that is known in advance in live trading, unlike prices.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trading_ai.indicators import atr, sma
from trading_ai.strategies.base import Strategy


class TurnOfMonth(Strategy):
    name = "turn_of_month"
    description = "Buy at the open N trading days before month end; sell at the open after trading day K of the new month."
    default_params = {
        "entry_days_before": 2,   # 1 = enter at the open of the month's last trading day
        "exit_day": 3,            # exit at the open of the trading day after this one
        "trend_len": 0,           # optional: only trade above this SMA (0 = off)
        "atr_len": 10,
        "stop_atr": 3.0,          # wide protective stop, prop firms require one
    }
    param_grid = {
        "entry_days_before": [1, 2, 3],
        "exit_day": [2, 3, 4],
    }
    max_bars = 10
    default_symbols = ("SPX500", "NAS100", "DOW30")

    def signals(self, bars: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        t = bars["time"].dt.tz_convert("UTC")
        month = t.dt.year * 12 + t.dt.month
        day_of_month = month.groupby(month).cumcount() + 1               # 1 = first trading day
        days_left = month.groupby(month).cumcount(ascending=False)       # 0 = last trading day
        in_trend = bars["close"] > sma(bars["close"], p["trend_len"]) if p["trend_len"] else True
        # Signal on the bar BEFORE the entry day; the engine fills at the next open.
        entry_day = days_left == p["entry_days_before"] - 1
        long_entry = entry_day.shift(-1, fill_value=False) & in_trend
        false = pd.Series(False, index=bars.index)
        return pd.DataFrame({
            "long_entry": long_entry,
            "short_entry": false,
            "long_exit": day_of_month == p["exit_day"],
            "short_exit": false,
            "stop_dist": p["stop_atr"] * atr(bars, p["atr_len"]),
            "target_dist": np.nan,
        }, index=bars.index)
