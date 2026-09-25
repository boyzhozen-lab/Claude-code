"""Add market context to journal trades so wins and losses can be explained.

Uses only bars that had fully closed before the entry (no look-ahead), except
for MAE/MFE which by definition look at the bars during the trade.
"""

from __future__ import annotations

from typing import Callable

import pandas as pd

from trading_ai.timeutil import TIMEFRAME_MINUTES, trading_session

BarsLoader = Callable[[str, str], "pd.DataFrame | None"]

# Finest first: MAE/MFE are only as accurate as the bars used.
EXCURSION_TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1"]


def atr(df: pd.DataFrame, n: int) -> pd.Series:
    prev_close = df["close"].shift()
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(n).mean()


def _closed_before(df: pd.DataFrame, timeframe: str, t: pd.Timestamp) -> pd.DataFrame:
    return df[df["time"] + pd.Timedelta(minutes=TIMEFRAME_MINUTES[timeframe]) <= t]


class Enricher:
    def __init__(self, load_bars: BarsLoader):
        self._load = load_bars
        self._cache: dict[tuple[str, str], pd.DataFrame | None] = {}

    def _bars(self, symbol: str, timeframe: str) -> pd.DataFrame | None:
        key = (symbol, timeframe)
        if key not in self._cache:
            df = self._load(symbol, timeframe)
            if df is not None and not df.empty:
                df = df.sort_values("time", ignore_index=True)
                if timeframe == "H1":
                    df["atr_ratio"] = atr(df, 14) / atr(df, 100)
                if timeframe == "D1":
                    df["sma50"] = df["close"].rolling(50).mean()
                    df["sma200"] = df["close"].rolling(200).mean()
            self._cache[key] = df
        return self._cache[key]

    def context(self, trade: pd.Series) -> dict[str, object]:
        open_t: pd.Timestamp = trade["open_time"]
        close_t: pd.Timestamp = trade["close_time"]
        ctx: dict[str, object] = {
            "session": trading_session(open_t.to_pydatetime()),
            "weekday": open_t.day_name(),
            "duration_min": round((close_t - open_t).total_seconds() / 60, 2),
        }

        h1 = self._bars(trade["symbol"], "H1")
        if h1 is not None:
            prior = _closed_before(h1, "H1", open_t)
            if not prior.empty and pd.notna(prior["atr_ratio"].iloc[-1]):
                ctx["atr_ratio"] = round(float(prior["atr_ratio"].iloc[-1]), 4)

        d1 = self._bars(trade["symbol"], "D1")
        if d1 is not None:
            prior = _closed_before(d1, "D1", open_t)
            if not prior.empty and pd.notna(prior["sma200"].iloc[-1]):
                last = prior.iloc[-1]
                if last["close"] > last["sma50"] > last["sma200"]:
                    ctx["trend_d1"] = "up"
                elif last["close"] < last["sma50"] < last["sma200"]:
                    ctx["trend_d1"] = "down"
                else:
                    ctx["trend_d1"] = "mixed"

        ctx.update(self._excursions(trade))
        return ctx

    def _excursions(self, trade: pd.Series) -> dict[str, object]:
        for tf in EXCURSION_TIMEFRAMES:
            df = self._bars(trade["symbol"], tf)
            if df is None:
                continue
            span = pd.Timedelta(minutes=TIMEFRAME_MINUTES[tf])
            during = df[(df["time"] + span > trade["open_time"]) & (df["time"] < trade["close_time"])]
            if during.empty:
                continue
            entry = trade["entry_price"]
            if trade["direction"] == "long":
                mfe, mae = during["high"].max() - entry, entry - during["low"].min()
            else:
                mfe, mae = entry - during["low"].min(), during["high"].max() - entry
            # Bars only give an envelope; never report less than the realised move.
            realised = (trade["exit_price"] - entry) * (1 if trade["direction"] == "long" else -1)
            mfe, mae = max(mfe, realised, 0.0), max(mae, -realised, 0.0)
            out: dict[str, object] = {"mae_price": float(mae), "mfe_price": float(mfe)}
            sl = trade.get("sl")
            if pd.notna(sl) and sl and abs(entry - sl) > 0:
                risk = abs(entry - sl)
                out["mae_r"] = round(float(mae / risk), 3)
                out["mfe_r"] = round(float(mfe / risk), 3)
            return out
        return {}
