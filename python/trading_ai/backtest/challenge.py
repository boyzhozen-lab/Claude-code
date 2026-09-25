"""Monte Carlo simulation of a prop-firm challenge.

Takes the strategy's historical daily results (in R), reshuffles them in
blocks of consecutive days (to keep losing streaks realistic) and replays
thousands of challenges under the firm's rules.

Limitation: rules are checked on closed daily P&L. Real firms also count
floating losses intraday, which is why the live risk manager stops at 3%/day,
well before the 5% limit.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ChallengeRules:
    profit_target: float      # % of initial balance
    max_daily_loss: float     # %
    max_total_loss: float     # %
    min_trading_days: int
    max_days: int = 0         # trading days; 0 = no limit


@dataclass(frozen=True)
class SimResult:
    runs: int
    pass_rate: float
    fail_daily: float
    fail_total: float
    unresolved: float         # neither passed nor failed within the horizon
    median_days: float        # among passes
    p90_days: float


NO_LIMIT_HORIZON = 250  # about one year of trading days


def simulate(
    daily_r: np.ndarray,
    risk_pct: float,
    rules: ChallengeRules,
    runs: int = 10_000,
    block: int = 5,
    seed: int = 0,
) -> SimResult:
    daily_r = np.asarray(daily_r, dtype=float)
    if len(daily_r) == 0:
        raise ValueError("No daily results to simulate")
    horizon = rules.max_days or NO_LIMIT_HORIZON
    block = max(1, min(block, len(daily_r)))
    n_blocks = -(-horizon // block)
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, len(daily_r) - block + 1, size=(runs, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)).reshape(runs, -1)[:, :horizon]
    day_pct = daily_r[idx] * risk_pct
    cum = np.cumsum(day_pct, axis=1)
    traded_days = np.cumsum(day_pct != 0, axis=1)

    def first(mask: np.ndarray) -> np.ndarray:
        hit = mask.any(axis=1)
        return np.where(hit, mask.argmax(axis=1), horizon)

    t_daily = first(day_pct <= -rules.max_daily_loss)
    t_total = first(cum <= -rules.max_total_loss)
    t_pass = first((cum >= rules.profit_target) & (traded_days >= rules.min_trading_days))

    t_fail = np.minimum(t_daily, t_total)
    passed = t_pass < t_fail  # a pass on the same day as a breach counts as a fail
    failed = (t_fail < horizon) & ~passed
    pass_days = t_pass[passed] + 1
    return SimResult(
        runs=runs,
        pass_rate=passed.mean(),
        fail_daily=(failed & (t_daily <= t_total)).mean(),
        fail_total=(failed & (t_total < t_daily)).mean(),
        unresolved=(~passed & ~failed).mean(),
        median_days=float(np.median(pass_days)) if len(pass_days) else float("nan"),
        p90_days=float(np.percentile(pass_days, 90)) if len(pass_days) else float("nan"),
    )
