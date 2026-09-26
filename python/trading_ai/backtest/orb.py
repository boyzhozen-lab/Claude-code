"""Backtest of USTEC_ORB_EA v1.6 (New York opening-range breakout) on M5 bars.

Mirrors the EA's rules:
- opening range = the M5 bar(s) from 09:30 New York time for `orb_minutes`
  (New York clock, so US daylight-saving shifts are handled)
- signal: an M5 bar closing above the range high (buy) or below the low (sell),
  evaluated once per closed bar from the end of the range until `entry_end`;
  entry at the next bar's open; at most one trade per day
- filters (all on the signal bar): range size in % of price, D1 EMA bias,
  momentum (body % and close position), tick volume vs the previous 20 bars
- stop: other side of the range +/- `sl_buffer_pts`; target: range x `tp_rr`
  from the entry; stop to break-even at `be_rr`, then trail by `trail_pts`
- everything still open is closed at `close_time` New York
Account-level brakes (daily loss, pauses) are left to the risk manager.

Bars only show high/low, not their order, so intrabar ties are resolved
against the trade: the stop is checked before the target, and a stop moved
inside a bar counts as hit if that bar closes beyond it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from trading_ai.backtest.engine import BacktestTrade

NY = "America/New_York"


@dataclass(frozen=True)
class OrbParams:
    open_hm: tuple[int, int] = (9, 30)
    orb_minutes: int = 5
    entry_end_hm: tuple[int, int] = (11, 0)
    close_hm: tuple[int, int] = (11, 0)
    use_d1_filter: bool = True
    d1_ema: int = 21
    use_mom_filter: bool = True
    mom_body_pct: float = 50.0
    mom_close_pct: float = 60.0
    use_volume_filter: bool = True
    volume_ma: int = 20
    volume_mult: float = 1.0
    min_range_pct: float = 0.03
    max_range_pct: float = 1.00
    tp_rr: float = 2.0
    be_rr: float = 1.0
    use_trail: bool = True
    trail_pts: float = 100.0
    # A trail tighter than normal tick noise is exited almost at once. False =
    # pessimistic: exit at the break-even trigger minus the trail, never higher.
    trail_from_bar_high: bool = True
    sl_buffer_pts: float = 5.0
    point: float = 0.01


def d1_bias(d1: pd.DataFrame, ema_len: int) -> pd.Series:
    """Bias per UTC calendar day, from the two daily bars before it (like the EA's shift 1/2)."""
    ema = d1["close"].ewm(span=ema_len, adjust=False).mean()
    c1, e1, e2 = d1["close"].shift(1), ema.shift(1), ema.shift(2)
    bias = np.where((c1 > e1) & (e1 > e2), 1, np.where((c1 < e1) & (e1 < e2), -1, 0))
    return pd.Series(bias, index=d1["time"].dt.tz_convert("UTC").dt.normalize())


def _minutes(hm: tuple[int, int]) -> int:
    return hm[0] * 60 + hm[1]


def orb_backtest(m5: pd.DataFrame, d1: pd.DataFrame | None, symbol: str, cost: float = 0.0,
                 p: OrbParams = OrbParams()) -> list[BacktestTrade]:
    df = m5.sort_values("time", ignore_index=True)
    ny = df["time"].dt.tz_convert(NY)
    minute = (ny.dt.hour * 60 + ny.dt.minute).to_numpy()
    day = ny.dt.date.to_numpy()
    o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    vol = df["tick_volume"].to_numpy(float)
    vol_avg = df["tick_volume"].shift(1).rolling(p.volume_ma).mean().to_numpy()
    utc_day = df["time"].dt.tz_convert("UTC").dt.normalize()
    bias = (utc_day.map(d1_bias(d1, p.d1_ema)).fillna(0).to_numpy() if (d1 is not None and p.use_d1_filter)
            else np.zeros(len(df)))

    orb_start, orb_end = _minutes(p.open_hm), _minutes(p.open_hm) + p.orb_minutes
    entry_end, close_at = _minutes(p.entry_end_hm), _minutes(p.close_hm)
    buffer, trail = p.sl_buffer_pts * p.point, p.trail_pts * p.point

    trades: list[BacktestTrade] = []
    day_starts = np.flatnonzero(np.r_[True, day[1:] != day[:-1]])
    day_ends = np.r_[day_starts[1:], len(df)]
    for s, e in zip(day_starts, day_ends):
        idx = np.arange(s, e)
        in_orb = idx[(minute[idx] >= orb_start) & (minute[idx] < orb_end)]
        if len(in_orb) == 0:
            continue
        oh, ol = h[in_orb].max(), l[in_orb].min()
        rng = oh - ol
        mid = (oh + ol) / 2
        if rng <= 0 or not (p.min_range_pct <= rng / mid * 100 <= p.max_range_pct):
            continue

        # Signal bars: closed after the range, evaluated while the NEXT bar opens before entry_end.
        entry_i = direction = None
        for i in idx[(minute[idx] >= orb_end)]:
            if i + 1 >= e or minute[i + 1] >= entry_end:
                break
            sig = 1 if c[i] > oh else -1 if c[i] < ol else 0
            if sig == 0:
                continue
            if bias[i] == -sig:
                continue
            if p.use_volume_filter and np.isfinite(vol_avg[i]) and vol_avg[i] > 0 and vol[i] < p.volume_mult * vol_avg[i]:
                continue
            if p.use_mom_filter and h[i] > l[i]:
                body = abs(c[i] - o[i]) / (h[i] - l[i]) * 100
                pos = (c[i] - l[i]) / (h[i] - l[i]) * 100
                close_ok = pos >= p.mom_close_pct if sig == 1 else pos <= 100 - p.mom_close_pct
                if body < p.mom_body_pct or not close_ok:
                    continue
            entry_i, direction = i + 1, sig
            break
        if entry_i is None:
            continue

        # Work in "favourable" coordinates (price x direction): higher is better for both sides.
        d = direction
        entry = o[entry_i]
        stop_px = ol - buffer if d == 1 else oh + buffer
        dist = d * (entry - stop_px)
        if dist <= 0:
            continue
        entry_f, stop_f = d * entry, d * stop_px
        target_f = entry_f + rng * p.tp_rr
        be_f = entry_f + p.be_rr * dist
        be_done = False
        mae = mfe = 0.0
        exit_i, exit_f, reason = e - 1, d * c[e - 1], "end"
        for j in range(entry_i, e):
            if minute[j] >= close_at:
                exit_i, exit_f, reason = j, d * o[j], "time"
                break
            open_f = d * o[j]
            hi_f, lo_f = (h[j], l[j]) if d == 1 else (-l[j], -h[j])
            if lo_f <= stop_f:
                exit_i, exit_f, reason = j, min(open_f, stop_f), ("trail" if p.use_trail else "be") if be_done else "sl"
                break
            if hi_f >= target_f:
                exit_i, exit_f, reason = j, max(open_f, target_f), "tp"
                break
            mae, mfe = max(mae, entry_f - lo_f), max(mfe, hi_f - entry_f)
            if not be_done and hi_f >= be_f:
                be_done = True
                stop_f = max(stop_f, entry_f + p.point)
                if p.use_trail and trail > 0:
                    if not p.trail_from_bar_high:
                        exit_i, exit_f, reason = j, max(open_f, be_f) - trail, "trail"
                        break
                    # the bar's high came after the break-even level was crossed
                    stop_f = max(stop_f, hi_f - trail)
            elif be_done and p.use_trail and trail > 0:
                stop_f = max(stop_f, hi_f - trail)
            if be_done and d * c[j] <= stop_f:   # stop moved inside this bar and the bar closed beyond it
                exit_i, exit_f, reason = j, stop_f, "trail" if p.use_trail else "be"
                break
        exit_px = d * exit_f
        move = d * (exit_px - entry)
        mae, mfe = max(mae, -move, 0.0), max(mfe, move, 0.0)
        trades.append(BacktestTrade(
            strategy="ustec_orb", symbol=symbol, direction="long" if d == 1 else "short",
            entry_time=df["time"].iloc[entry_i], exit_time=df["time"].iloc[exit_i],
            entry_price=entry, exit_price=exit_px, stop_price=stop_px,
            target_price=d * target_f, stop_dist=dist, exit_reason=reason, bars_held=exit_i - entry_i,
            gross_r=move / dist, swap_r=0.0, r=(move - cost) / dist, mae_r=mae / dist, mfe_r=mfe / dist,
        ))
    return trades
