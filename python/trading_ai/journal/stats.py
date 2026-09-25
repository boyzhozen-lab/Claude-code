"""Performance summaries of journal trades."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _summary(g: pd.DataFrame) -> pd.Series:
    wins = g.loc[g["net_profit"] > 0, "net_profit"]
    losses = g.loc[g["net_profit"] < 0, "net_profit"]
    r = g["r_multiple"].dropna()
    return pd.Series({
        "trades": len(g),
        "win_rate": len(wins) / len(g) if len(g) else np.nan,
        "net_profit": g["net_profit"].sum(),
        "avg_trade": g["net_profit"].mean(),
        "avg_win": wins.mean() if len(wins) else np.nan,
        "avg_loss": losses.mean() if len(losses) else np.nan,
        "profit_factor": wins.sum() / -losses.sum() if len(losses) else np.inf if len(wins) else np.nan,
        "avg_r": r.mean() if len(r) else np.nan,
    })


def summarize(trades: pd.DataFrame, by: str | None = None) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    if by is None:
        return _summary(trades).to_frame("all").T
    if by not in trades.columns:
        raise ValueError(f"Cannot group by '{by}'")
    groups = trades.assign(**{by: trades[by].fillna("(unknown)")}).groupby(by, sort=True)
    return pd.DataFrame({name: _summary(g) for name, g in groups}).T.rename_axis(by)


def max_drawdown(trades: pd.DataFrame) -> float:
    """Largest peak-to-trough fall of cumulative net profit, in account currency."""
    if trades.empty:
        return 0.0
    equity = trades.sort_values("close_time")["net_profit"].cumsum()
    peak = equity.cummax().clip(lower=0)
    return float((peak - equity).max())
