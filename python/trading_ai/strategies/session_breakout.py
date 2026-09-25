"""Strategy C: session opening-range breakout on intraday (H1) bars.

Each day: measure the high/low of a quiet "range" window, trade the first
close outside it during the entry window, and be flat before the day ends.
All hours are UTC, so sessions shift by one hour when Europe/US change to
or from daylight saving time.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trading_ai.strategies.base import Strategy


class SessionBreakout(Strategy):
    name = "london_breakout"
    description = "Asian-session range (00-07 UTC), trade the first break during London (07-12), flat by 20 UTC."
    default_params = {
        "range_start": 0,     # UTC hour, inclusive
        "range_end": 7,       # UTC hour, exclusive; entries allowed from here
        "entry_end": 12,      # no new entries from this hour
        "flat_hour": 20,      # close any position at this hour's open
        "stop_frac": 1.0,     # stop distance = range width x stop_frac
        "target_r": 0.0,      # target in R; 0 = no target, exit at flat_hour
        "min_range_frac": 0.0005,  # skip days whose range is < this fraction of price (dead market)
    }
    param_grid = {
        "stop_frac": [0.5, 1.0],
        "target_r": [0.0, 1.5, 3.0],
    }
    max_bars = 24  # safety net: never hold overnight
    default_timeframe = "H1"
    default_symbols = ("GOLD", "GBPUSD", "EURUSD")

    def signals(self, bars: pd.DataFrame) -> pd.DataFrame:
        step = bars["time"].diff().median()
        if pd.notna(step) and step > pd.Timedelta(hours=1):
            raise ValueError(f"{self.name} needs H1 (or finer) bars, got {step} spacing")
        p = self.params
        hour = bars["time"].dt.hour
        day = bars["time"].dt.normalize()

        in_range = (hour >= p["range_start"]) & (hour < p["range_end"])
        range_high = bars["high"].where(in_range).groupby(day).transform("max")
        range_low = bars["low"].where(in_range).groupby(day).transform("min")
        width = range_high - range_low
        # The range is only known once its last bar has closed.
        range_done = hour >= p["range_end"]
        wide_enough = width >= p["min_range_frac"] * bars["close"]

        can_enter = range_done & (hour < p["entry_end"]) & wide_enough
        up = can_enter & (bars["close"] > range_high)
        down = can_enter & (bars["close"] < range_low)
        # Exit at the open of flat_hour: signal on the bar before it, or on the
        # day's last bar (e.g. Friday close / holidays) so nothing is held overnight.
        last_of_day = day != day.shift(-1)

        # Only the first breakout of each day, in either direction, and never on
        # the day's last bar (the fill would land on the next day).
        first = (up | down) & ((up | down).astype(int).groupby(day).cumsum() == 1) & ~last_of_day
        flat = (hour >= p["flat_hour"] - 1) | last_of_day

        stop_dist = p["stop_frac"] * width
        target = stop_dist * p["target_r"] if p["target_r"] > 0 else pd.Series(np.nan, index=bars.index)
        return pd.DataFrame({
            "long_entry": first & up,
            "short_entry": first & down,
            "long_exit": flat,
            "short_exit": flat,
            "stop_dist": stop_dist,
            "target_dist": target,
        }, index=bars.index)


class NYBreakout(SessionBreakout):
    name = "ny_breakout"
    description = "US-open range (13-15 UTC), trade the first break until 18 UTC, flat by 20 UTC."
    default_params = SessionBreakout.default_params | {
        "range_start": 13,
        "range_end": 15,
        "entry_end": 18,
        "flat_hour": 20,
    }
    default_symbols = ("NAS100", "SPX500", "DOW30", "GOLD")
