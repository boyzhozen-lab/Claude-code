import numpy as np
import pandas as pd
import pytest

from trading_ai.backtest.orb import OrbParams, d1_bias, orb_backtest

P = OrbParams(point=0.01, use_d1_filter=False, use_volume_filter=False)


def ny_day(date, bars, base=20000.0):
    """M5 bars from 09:00 to 12:00 New York. `bars` maps 'HH:MM' -> (o, h, l, c)."""
    times = pd.date_range(f"{date} 09:00", f"{date} 12:00", freq="5min", tz="America/New_York", inclusive="left")
    rows = []
    for t in times:
        o, hi, lo, c = bars.get(t.strftime("%H:%M"), (base, base + 1, base - 1, base))
        rows.append((t.tz_convert("UTC"), o, hi, lo, c, 100))
    return pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "tick_volume"])


RANGE = {"09:30": (20000, 20020, 19980, 20010)}           # 40-point opening range
BREAK_UP = {"09:35": (20010, 20031, 20009, 20030)}        # strong close above 20020


def test_long_breakout_hits_target_without_trailing():
    bars = {**RANGE, **BREAK_UP,
            "09:40": (20030, 20040, 20025, 20035),          # entry at 20030, stop 19979.95
            "09:45": (20035, 20115, 20030, 20110)}          # target 20030 + 2*40 = 20110
    [t] = orb_backtest(ny_day("2024-07-10", bars), None, "NAS100", 0.0,
                       OrbParams(point=0.01, use_d1_filter=False, use_volume_filter=False, use_trail=False, be_rr=1e9))
    assert t.direction == "long" and t.entry_price == 20030
    assert t.entry_time == pd.Timestamp("2024-07-10 13:40", tz="UTC")   # 09:40 EDT
    assert t.stop_price == pytest.approx(19979.95)
    assert t.exit_reason == "tp" and t.exit_price == pytest.approx(20110)
    assert t.r == pytest.approx(80 / 50.05)


def test_one_point_trail_exits_right_after_break_even():
    bars = {**RANGE, **BREAK_UP,
            "09:40": (20030, 20085, 20028, 20082),          # passes +1R (20080.05) inside the bar
            "09:45": (20082, 20100, 20060, 20095)}
    [t] = orb_backtest(ny_day("2024-07-10", bars), None, "NAS100", 0.0, P)
    assert t.exit_reason == "trail"
    # trail = 100 points x 0.01 = 1.0 index point below the 20085 high; the bar closes below it
    assert t.exit_price == pytest.approx(20084.0)
    assert t.exit_time == pd.Timestamp("2024-07-10 13:40", tz="UTC")
    assert t.r == pytest.approx(54 / 50.05)


def test_time_exit_at_11_new_york_and_winter_time():
    bars = {**RANGE, **BREAK_UP}
    [t] = orb_backtest(ny_day("2024-01-10", bars), None, "NAS100", 0.0, P)
    assert t.entry_time == pd.Timestamp("2024-01-10 14:40", tz="UTC")   # 09:40 EST
    assert t.exit_reason == "time" and t.exit_time == pd.Timestamp("2024-01-10 16:00", tz="UTC")


def test_short_breakout_stop_loss():
    bars = {**RANGE,
            "09:35": (19990, 19991, 19969, 19970),
            "09:40": (19970, 20025, 19965, 20020)}          # stop at 20020.05 hit
    [t] = orb_backtest(ny_day("2024-07-10", bars), None, "NAS100", 0.0, P)
    assert t.direction == "short" and t.exit_reason == "sl"
    assert t.r == pytest.approx(-1.0)


def test_filters_momentum_range_and_one_trade_per_day():
    weak = {**RANGE, "09:35": (20010, 20040, 20000, 20021)}   # close barely above, weak body
    assert orb_backtest(ny_day("2024-07-10", weak), None, "NAS100", 0.0, P) == []
    tiny = {"09:30": (20000, 20001, 19999, 20000), **BREAK_UP}  # range 0.01% < 0.03%
    assert orb_backtest(ny_day("2024-07-10", tiny), None, "NAS100", 0.0, P) == []
    two = {**RANGE, **BREAK_UP, "09:40": (20030, 20032, 19975, 19976), "09:45": (19976, 19977, 19950, 19952)}
    trades = orb_backtest(ny_day("2024-07-10", two), None, "NAS100", 0.0, P)
    assert len(trades) == 1


def test_no_entry_after_entry_window():
    late = {**RANGE, "10:55": (20010, 20031, 20009, 20030)}
    assert orb_backtest(ny_day("2024-07-10", late), None, "NAS100", 0.0, P) == []
    ok = {**RANGE, "10:50": (20010, 20031, 20009, 20030)}   # evaluated at 10:55, still before 11:00
    assert len(orb_backtest(ny_day("2024-07-10", ok), None, "NAS100", 0.0, P)) == 1


def test_d1_bias_blocks_counter_trend_trades():
    days = pd.date_range("2024-05-01", periods=60, freq="D", tz="UTC")
    falling = pd.DataFrame({"time": days, "close": np.linspace(21000, 20000, 60)})
    assert d1_bias(falling, 21).iloc[-1] == -1
    bars = {**RANGE, **BREAK_UP}
    m5 = ny_day("2024-06-29", bars)
    params = OrbParams(point=0.01, use_volume_filter=False)
    assert orb_backtest(m5, falling, "NAS100", 0.0, params) == []
    rising = falling.assign(close=np.linspace(20000, 21000, 60))
    assert len(orb_backtest(m5, rising, "NAS100", 0.0, params)) == 1


def test_pessimistic_trail_exits_at_break_even_trigger():
    bars = {**RANGE, **BREAK_UP,
            "09:40": (20030, 20085, 20028, 20082),
            "09:45": (20082, 20100, 20060, 20095)}
    [t] = orb_backtest(ny_day("2024-07-10", bars), None, "NAS100", 0.0,
                       OrbParams(point=0.01, use_d1_filter=False, use_volume_filter=False, trail_from_bar_high=False))
    assert t.exit_price == pytest.approx(20080.05 - 1.0)
    assert t.r == pytest.approx((50.05 - 1.0) / 50.05)
