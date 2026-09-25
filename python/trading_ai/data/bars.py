"""Store, load and sanity-check OHLC bars as CSV files (times in UTC)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from trading_ai.timeutil import server_series_to_utc

BAR_COLUMNS = ["time", "open", "high", "low", "close", "tick_volume", "spread"]
LARGE_GAP = pd.Timedelta(days=4)  # longer than a weekend plus a holiday


def bars_path(bars_dir: Path, internal_symbol: str, timeframe: str) -> Path:
    return bars_dir / f"{internal_symbol}_{timeframe}.csv"


def normalize_rates(raw: pd.DataFrame, server_tz: str) -> pd.DataFrame:
    df = raw.copy()
    df["time"] = server_series_to_utc(df["time"], server_tz)
    return df[BAR_COLUMNS].sort_values("time", ignore_index=True)


def load_bars(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["time"], utc=True, format="ISO8601")
    return df


def save_bars(new: pd.DataFrame, path: Path) -> pd.DataFrame:
    """Merge with any existing file (newer rows win) and write it back."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.concat([load_bars(path), new], ignore_index=True) if path.exists() else new
    df = df.drop_duplicates("time", keep="last").sort_values("time", ignore_index=True)
    out = df.copy()
    out["time"] = out["time"].map(lambda t: t.isoformat())
    out.to_csv(path, index=False)
    return df


def validate_bars(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {"rows": 0, "problems": ["no data"]}
    t = df["time"]
    gaps = t.diff()
    large = df.loc[gaps > LARGE_GAP, "time"]
    bad_ohlc = (
        (df["high"] < df["low"])
        | (df["high"] < df[["open", "close"]].max(axis=1))
        | (df["low"] > df[["open", "close"]].min(axis=1))
        | (df[["open", "high", "low", "close"]] <= 0).any(axis=1)
    )
    problems = []
    if t.duplicated().any():
        problems.append(f"{int(t.duplicated().sum())} duplicate timestamps")
    if bad_ohlc.any():
        problems.append(f"{int(bad_ohlc.sum())} bars with invalid OHLC")
    for end in large.head(5):
        start = t[t < end].iloc[-1]
        problems.append(f"gap {start:%Y-%m-%d} -> {end:%Y-%m-%d}")
    return {
        "rows": len(df),
        "start": t.iloc[0],
        "end": t.iloc[-1],
        "large_gaps": len(large),
        "problems": problems,
    }
