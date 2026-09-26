"""Bar-by-bar backtest engine, one position at a time.

Rules, chosen to be conservative rather than flattering:
- Signals are read at a bar's close and acted on at the next bar's open.
- A stop that the market gaps through fills at the (worse) open price.
- If the stop and the target are both inside one bar, the stop is assumed hit first.
- Costs (spread + commission + slippage, round trip, in price units) are
  subtracted from every trade.
- Overnight swap is charged per weekday rollover held (triple on the broker's
  triple-swap day), when swap rates are given.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from trading_ai.strategies.base import Strategy


@dataclass
class BacktestTrade:
    strategy: str
    symbol: str
    direction: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    stop_price: float
    target_price: float | None
    stop_dist: float
    exit_reason: str       # sl | tp | signal | time | end
    bars_held: int
    gross_r: float
    swap_r: float          # overnight financing, in R (negative = paid)
    r: float               # after costs and swap
    mae_r: float
    mfe_r: float


@dataclass
class _Open:
    direction: int  # +1 long, -1 short
    entry_i: int
    entry: float
    stop: float
    target: float | None
    dist: float
    bars: int = 0
    mae: float = 0.0
    mfe: float = 0.0


def nights_held(entry: pd.Timestamp, exit_: pd.Timestamp, triple_weekday: int = 2) -> int:
    """Swap nights between two times: one per weekday rollover (midnight UTC),
    three on the triple-swap weekday, none on Saturday/Sunday."""
    first, last = entry.normalize(), exit_.normalize()
    if last <= first:
        return 0
    days = pd.date_range(first, last - pd.Timedelta(days=1), freq="D")
    return int(sum(3 if d.weekday() == triple_weekday else 1 for d in days if d.weekday() < 5))


def run_backtest(
    bars: pd.DataFrame,
    strategy: Strategy,
    symbol: str,
    cost: float = 0.0,
    swap_long: float = 0.0,     # price units per night, positive = received
    swap_short: float = 0.0,
    triple_weekday: int = 2,
) -> list[BacktestTrade]:
    bars = bars.reset_index(drop=True)
    sig = strategy.signals(bars)
    o, h, l, c = (bars[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    times = bars["time"]
    le, se, lx, sx = (sig[k].fillna(False).to_numpy(bool) for k in ("long_entry", "short_entry", "long_exit", "short_exit"))
    sd = sig["stop_dist"].to_numpy(float)
    td = sig["target_dist"].to_numpy(float)
    max_bars = strategy.max_bars

    trades: list[BacktestTrade] = []
    pos: _Open | None = None

    def close(i: int, price: float, reason: str) -> None:
        nonlocal pos
        assert pos is not None
        move = pos.direction * (price - pos.entry)
        nightly = swap_long if pos.direction > 0 else swap_short
        swap = nightly * nights_held(times[pos.entry_i], times[i], triple_weekday) if nightly else 0.0
        mae = max(pos.mae, -move)
        mfe = max(pos.mfe, move)
        trades.append(BacktestTrade(
            strategy=strategy.name, symbol=symbol,
            direction="long" if pos.direction > 0 else "short",
            entry_time=times[pos.entry_i], exit_time=times[i],
            entry_price=pos.entry, exit_price=price, stop_price=pos.stop, target_price=pos.target,
            stop_dist=pos.dist, exit_reason=reason, bars_held=pos.bars,
            gross_r=move / pos.dist, swap_r=swap / pos.dist, r=(move - cost + swap) / pos.dist,
            mae_r=max(mae, 0.0) / pos.dist, mfe_r=max(mfe, 0.0) / pos.dist,
        ))
        pos = None

    for i in range(1, len(bars)):
        p = i - 1
        # 1. Exits decided at the previous close happen at this open.
        if pos is not None:
            wants_exit = lx[p] if pos.direction > 0 else sx[p]
            if wants_exit:
                close(i, o[i], "signal")
            elif max_bars and pos.bars >= max_bars:
                close(i, o[i], "time")

        # 2. Entries decided at the previous close happen at this open.
        if pos is None and np.isfinite(sd[p]) and sd[p] > 0:
            direction = 1 if le[p] else -1 if se[p] else 0
            if direction:
                entry = o[i]
                target = entry + direction * td[p] if np.isfinite(td[p]) and td[p] > 0 else None
                pos = _Open(direction, i, entry, entry - direction * sd[p], target, sd[p])

        # 3. Stop / target inside this bar.
        if pos is not None:
            if pos.direction > 0:
                if l[i] <= pos.stop:
                    close(i, min(o[i], pos.stop), "sl")
                elif pos.target is not None and h[i] >= pos.target:
                    close(i, max(o[i], pos.target), "tp")
            else:
                if h[i] >= pos.stop:
                    close(i, max(o[i], pos.stop), "sl")
                elif pos.target is not None and l[i] <= pos.target:
                    close(i, min(o[i], pos.target), "tp")
            if pos is not None:
                if pos.direction > 0:
                    pos.mae, pos.mfe = max(pos.mae, pos.entry - l[i]), max(pos.mfe, h[i] - pos.entry)
                else:
                    pos.mae, pos.mfe = max(pos.mae, h[i] - pos.entry), max(pos.mfe, pos.entry - l[i])
                pos.bars += 1

    if pos is not None:
        close(len(bars) - 1, c[-1], "end")
    return trades


def trades_frame(trades: list[BacktestTrade]) -> pd.DataFrame:
    cols = list(BacktestTrade.__dataclass_fields__)
    return pd.DataFrame([asdict(t) for t in trades], columns=cols)
