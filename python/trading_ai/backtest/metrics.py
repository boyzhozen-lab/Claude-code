"""Performance metrics for backtest trades (R-multiples and % of balance)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def daily_r(trades: pd.DataFrame) -> pd.Series:
    """Sum of R per business day (by exit date), including days without trades."""
    if trades.empty:
        return pd.Series(dtype=float)
    day = trades["exit_time"].dt.tz_convert("UTC").dt.normalize().dt.tz_localize(None)
    per_day = trades.groupby(day)["r"].sum()
    start = trades["entry_time"].min().tz_convert("UTC").normalize().tz_localize(None)
    days = pd.bdate_range(start, per_day.index.max())
    # Weekend exits (rare, e.g. crypto) are folded onto the calendar as-is.
    return per_day.reindex(days.union(per_day.index), fill_value=0.0)


def _longest_losing_streak(r: np.ndarray) -> int:
    best = cur = 0
    for x in r:
        cur = cur + 1 if x < 0 else 0
        best = max(best, cur)
    return best


def performance(trades: pd.DataFrame, risk_pct: float) -> dict[str, float]:
    """risk_pct: % of initial balance risked per trade (fixed, not compounded)."""
    if trades.empty:
        return {"trades": 0}
    t = trades.sort_values("exit_time")
    r = t["r"].to_numpy()
    wins, losses = r[r > 0], r[r < 0]
    equity = np.cumsum(r) * risk_pct
    peak = np.maximum.accumulate(np.concatenate([[0.0], equity]))[1:]
    years = max((t["exit_time"].max() - t["entry_time"].min()).days / 365.25, 1 / 365.25)
    d = daily_r(t) * risk_pct
    return {
        "trades": len(r),
        "trades_per_year": len(r) / years,
        "win_rate": len(wins) / len(r),
        "avg_r": r.mean(),
        "profit_factor": wins.sum() / -losses.sum() if len(losses) else np.inf,
        "total_r": r.sum(),
        "return_pct": equity[-1],
        "return_pct_per_year": equity[-1] / years,
        "max_dd_pct": float((peak - equity).max()),
        "worst_day_pct": float(d.min()),
        "losing_streak": _longest_losing_streak(r),
        "swap_r": float(t["swap_r"].sum()) if "swap_r" in t else 0.0,
        "years": years,
    }
