"""Walk-forward testing: pick parameters on past data, judge them on the next,
unseen period, then roll forward. Only the unseen-period trades count, which
is a far more honest estimate than the best in-sample result.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from trading_ai.backtest.engine import run_backtest, trades_frame
from trading_ai.strategies.base import Strategy


@dataclass
class Fold:
    train_start: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    params: dict
    train_r: float
    test_r: float
    test_trades: int


@dataclass
class WalkForwardResult:
    oos_trades: pd.DataFrame
    folds: list[Fold] = field(default_factory=list)


def param_combos(strategy_cls: type[Strategy]) -> list[dict]:
    keys = list(strategy_cls.param_grid)
    return [dict(zip(keys, values)) for values in itertools.product(*strategy_cls.param_grid.values())]


def _in(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    return df[(df["entry_time"] >= start) & (df["entry_time"] < end)]


def walk_forward(
    bars: pd.DataFrame,
    strategy_cls: type[Strategy],
    symbol: str,
    cost: float = 0.0,
    train_years: int = 3,
    test_years: int = 1,
    min_trades: int = 10,
) -> WalkForwardResult:
    # Indicators are causal, so one full-history run per parameter set is
    # equivalent to re-running each window separately (and much faster).
    runs = []
    for params in param_combos(strategy_cls):
        runs.append((params, trades_frame(run_backtest(bars, strategy_cls(**params), symbol, cost))))

    first, last = bars["time"].iloc[0], bars["time"].iloc[-1]
    result = WalkForwardResult(oos_trades=trades_frame([]))
    oos_parts = []
    train_start = first
    while True:
        test_start = train_start + pd.DateOffset(years=train_years)
        test_end = test_start + pd.DateOffset(years=test_years)
        if test_start >= last:
            break
        best_params, best_score, best_trades = None, -np.inf, None
        for params, trades in runs:
            train = _in(trades, train_start, test_start)
            score = train["r"].sum() if len(train) >= min_trades else -np.inf
            if score > best_score:
                best_params, best_score, best_trades = params, score, trades
        if best_params is not None:
            test = _in(best_trades, test_start, test_end)
            oos_parts.append(test)
            result.folds.append(Fold(train_start, test_start, min(test_end, last), best_params,
                                     float(best_score), float(test["r"].sum()), len(test)))
        train_start += pd.DateOffset(years=test_years)
    if oos_parts:
        result.oos_trades = pd.concat(oos_parts, ignore_index=True)
    return result
