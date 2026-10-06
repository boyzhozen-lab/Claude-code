"""Market intraday momentum (Gao, Han, Li & Zhou, Journal of Financial Economics 2018):
the S&P 500's return from the previous close to the first half hour of trading
predicts the direction of its last half hour. One short trade a day, flat by the close.

Times are New York wall clock (DST handled). Needs intraday bars (M15 or finer).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trading_ai.indicators import atr
from trading_ai.strategies.base import Strategy

NY = "America/New_York"
CLOSE_MIN = 16 * 60  # 16:00 New York cash close


class IntradayMomentum(Strategy):
    name = "intraday_momentum"
    description = "Trade the last part of the US session in the direction of (previous close -> 10:00 NY)."
    default_params = {
        "signal_end": 600,    # minutes after midnight NY: 10:00
        "entry": 930,         # 15:30
        "exit": 960,          # 16:00
        "min_move": 0.0,      # minimum |first-period return| to trade, as a fraction (0.002 = 0.2%)
        "atr_len": 14,
        "stop_atr": 3.0,      # protective stop; rarely reached in half an hour
    }
    param_grid = {
        "entry": [900, 930],          # 15:00 or 15:30
        "min_move": [0.0, 0.002],
    }
    max_bars = 12
    default_timeframe = "M15"
    default_symbols = ("SPX500", "NAS100", "DOW30")

    def signals(self, bars: pd.DataFrame) -> pd.DataFrame:
        step = bars["time"].diff().median()
        if pd.isna(step) or step > pd.Timedelta(minutes=30):
            raise ValueError(f"{self.name} needs M15 (or finer) bars, got {step} spacing")
        step_min = int(step / pd.Timedelta(minutes=1))
        p = self.params
        ny = bars["time"].dt.tz_convert(NY)
        minute = (ny.dt.hour * 60 + ny.dt.minute).to_numpy()
        day = ny.dt.normalize()
        close = bars["close"]

        def close_at(end_minute: int) -> pd.Series:
            """Per NY day: close of the bar that ends at end_minute."""
            rows = minute == end_minute - step_min
            return pd.Series(close[rows].to_numpy(), index=day[rows].to_numpy()).groupby(level=0).last()

        prev_close = close_at(CLOSE_MIN).shift(1)          # previous trading day's 16:00 close
        first = close_at(p["signal_end"])
        first_ret = (first / prev_close - 1).reindex(day.to_numpy()).to_numpy()

        signal_bar = minute == p["entry"] - step_min       # closes at the entry time; fill at next open
        go = signal_bar & np.isfinite(first_ret) & (np.abs(first_ret) > p["min_move"])
        exit_bar = minute >= p["exit"] - step_min
        last_of_day = (day != day.shift(-1)).to_numpy()
        flat = exit_bar | last_of_day
        return pd.DataFrame({
            "long_entry": go & (first_ret > 0) & ~last_of_day,
            "short_entry": go & (first_ret < 0) & ~last_of_day,
            "long_exit": flat,
            "short_exit": flat,
            "stop_dist": p["stop_atr"] * atr(bars, p["atr_len"]),
            "target_dist": np.nan,
        }, index=bars.index)
