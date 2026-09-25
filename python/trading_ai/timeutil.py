"""Time helpers. Everything stored by this project is in UTC."""

from __future__ import annotations

from datetime import datetime, timezone, tzinfo
from zoneinfo import ZoneInfo

import pandas as pd

TIMEFRAME_MINUTES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
}


def get_tz(name: str) -> tzinfo:
    return timezone.utc if name.upper() == "UTC" else ZoneInfo(name)


def server_ts_to_utc(ts: float, server_tz: str) -> datetime:
    """MT5 returns server wall-clock time encoded as a Unix timestamp; convert to real UTC."""
    wall = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
    return wall.replace(tzinfo=get_tz(server_tz)).astimezone(timezone.utc)


def server_series_to_utc(ts: pd.Series, server_tz: str) -> pd.Series:
    wall = pd.to_datetime(ts, unit="s")
    if server_tz.upper() == "UTC":
        return wall.dt.tz_localize("UTC")
    try:
        local = wall.dt.tz_localize(server_tz, ambiguous="infer", nonexistent="shift_forward")
    except Exception:  # ambiguous DST hour that cannot be inferred
        local = wall.dt.tz_localize(server_tz, ambiguous=False, nonexistent="shift_forward")
    return local.dt.tz_convert("UTC")


def trading_session(dt_utc: datetime) -> str:
    """Approximate market session from the UTC hour (ignores DST shifts)."""
    h = dt_utc.astimezone(timezone.utc).hour
    if h < 7:
        return "asia"
    if h < 12:
        return "london"
    if h < 16:
        return "london_ny_overlap"
    if h < 21:
        return "new_york"
    return "late"


def to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def from_iso(s: str) -> datetime:
    return datetime.fromisoformat(s).astimezone(timezone.utc)
