import numpy as np
import pandas as pd
import pytest

from trading_ai.backtest.challenge import ChallengeRules, simulate
from trading_ai.backtest.engine import run_backtest, trades_frame
from trading_ai.backtest.metrics import daily_r, performance
from trading_ai.backtest.walkforward import walk_forward
from trading_ai.indicators import rsi
from trading_ai.strategies import RSI2Reversion, TrendBreakout
from trading_ai.strategies.base import Strategy


def ohlc(rows, start="2024-01-01"):
    """rows: list of (open, high, low, close)."""
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    df.insert(0, "time", pd.date_range(start, periods=len(rows), freq="D", tz="UTC"))
    return df


class Scripted(Strategy):
    """Enters long on given bar indices with a fixed stop/target distance."""
    name = "scripted"
    description = "test"
    default_params = {"entries": (), "exits": (), "stop": 5.0, "target": np.nan, "short": False}
    param_grid = {}

    def signals(self, bars):
        n = len(bars)
        entry = pd.Series(False, index=bars.index)
        entry.iloc[list(self.params["entries"])] = True
        exit_ = pd.Series(False, index=bars.index)
        exit_.iloc[list(self.params["exits"])] = True
        none = pd.Series(False, index=bars.index)
        short = self.params["short"]
        return pd.DataFrame({
            "long_entry": none if short else entry, "short_entry": entry if short else none,
            "long_exit": none if short else exit_, "short_exit": exit_ if short else none,
            "stop_dist": [self.params["stop"]] * n, "target_dist": [self.params["target"]] * n,
        }, index=bars.index)


FLAT = (100, 101, 99, 100)


def test_entry_is_next_open_and_stop_hit():
    bars = ohlc([FLAT, (102, 103, 101, 102), (102, 103, 96, 97)])
    [t] = run_backtest(bars, Scripted(entries=[0]), "X", cost=0.5)
    assert t.entry_price == 102 and t.stop_price == 97
    assert t.exit_reason == "sl" and t.exit_price == 97
    assert t.gross_r == pytest.approx(-1.0)
    assert t.r == pytest.approx(-1.1)
    assert t.mae_r == pytest.approx(1.0)


def test_gap_through_stop_fills_at_open():
    bars = ohlc([FLAT, FLAT, (90, 91, 89, 90)])
    [t] = run_backtest(bars, Scripted(entries=[0]), "X")
    assert t.exit_price == 90 and t.gross_r == pytest.approx(-2.0)


def test_stop_and_target_same_bar_assumes_stop():
    bars = ohlc([FLAT, FLAT, (100, 120, 90, 100)])
    [t] = run_backtest(bars, Scripted(entries=[0], target=10.0), "X")
    assert t.exit_reason == "sl"


def test_target_and_signal_exit_and_short():
    bars = ohlc([FLAT, FLAT, (100, 111, 99, 110)])
    [t] = run_backtest(bars, Scripted(entries=[0], target=10.0), "X")
    assert t.exit_reason == "tp" and t.gross_r == pytest.approx(2.0)

    bars = ohlc([FLAT, FLAT, (100, 101, 97, 98), (97, 98, 96, 97)])
    [t] = run_backtest(bars, Scripted(entries=[0], exits=[2], short=True), "X")
    assert t.direction == "short" and t.exit_reason == "signal"
    assert t.exit_price == 97 and t.gross_r == pytest.approx(0.6)
    assert t.mfe_r == pytest.approx(0.6)  # the exit bar is left at its open


def test_open_position_closed_at_end_and_no_overlap():
    bars = ohlc([FLAT] * 5)
    trades = run_backtest(bars, Scripted(entries=[0, 1, 2]), "X")
    assert len(trades) == 1 and trades[0].exit_reason == "end"


def test_time_exit():
    class Timed(Scripted):
        max_bars = 2
    bars = ohlc([FLAT] * 6)
    [t] = run_backtest(bars, Timed(entries=[0]), "X")
    assert t.exit_reason == "time" and t.bars_held == 2


def trending(n=400, slope=0.5, seed=1):
    rng = np.random.default_rng(seed)
    close = 100 + slope * np.arange(n) + rng.normal(0, 1, n).cumsum() * 0.2
    return ohlc([(c, c + 0.2, c - 0.2, c) for c in close], start="2018-01-01")


def test_trend_breakout_profits_in_a_trend():
    trades = trades_frame(run_backtest(trending(), TrendBreakout(), "X"))
    assert len(trades) > 0
    assert (trades["direction"] == "long").all()  # below-SMA shorts filtered out
    assert trades["r"].sum() > 0


def test_rsi2_long_only_and_uses_time_exit():
    trades = trades_frame(run_backtest(trending(800, slope=0.05, seed=3), RSI2Reversion(), "X"))
    assert len(trades) > 0
    assert set(trades["direction"]) == {"long"}
    assert trades["bars_held"].max() <= RSI2Reversion.max_bars


def test_rsi_bounds():
    r = rsi(pd.Series(np.linspace(1, 50, 30)), 2)
    assert r.dropna().eq(100).all()
    r = rsi(pd.Series(np.random.default_rng(0).normal(0, 1, 200).cumsum() + 100), 2).dropna()
    assert r.between(0, 100).all()


def test_unknown_strategy_param_rejected():
    with pytest.raises(ValueError):
        TrendBreakout(nonsense=1)


def fake_trades(rs, start="2024-01-01"):
    times = pd.date_range(start, periods=len(rs), freq="B", tz="UTC")
    return pd.DataFrame({"entry_time": times, "exit_time": times, "r": rs})


def test_performance_and_daily_series():
    trades = fake_trades([2.0, -1.0, -1.0, 3.0])
    perf = performance(trades, risk_pct=0.5)
    assert perf["trades"] == 4 and perf["win_rate"] == 0.5
    assert perf["profit_factor"] == pytest.approx(2.5)
    assert perf["return_pct"] == pytest.approx(1.5)
    assert perf["max_dd_pct"] == pytest.approx(1.0)
    assert perf["losing_streak"] == 2
    assert list(daily_r(trades)) == [2.0, -1.0, -1.0, 3.0]


RULES = ChallengeRules(profit_target=10, max_daily_loss=5, max_total_loss=10, min_trading_days=4)


def test_challenge_always_winning_passes():
    res = simulate(np.array([1.0] * 50), risk_pct=1.0, rules=RULES, runs=200)
    assert res.pass_rate == 1.0 and res.median_days == 10


def test_challenge_min_trading_days():
    res = simulate(np.array([20.0] * 10), risk_pct=1.0, rules=ChallengeRules(10, 50, 50, 4), runs=50)
    assert res.pass_rate == 1.0 and res.median_days == 4


def test_challenge_daily_and_total_failures():
    res = simulate(np.array([-6.0]), risk_pct=1.0, rules=RULES, runs=100)
    assert res.fail_daily == 1.0
    res = simulate(np.array([-1.0]), risk_pct=1.0, rules=RULES, runs=100)
    assert res.fail_total == 1.0 and res.pass_rate == 0.0


def test_challenge_higher_risk_trades_speed_for_safety():
    rng = np.random.default_rng(5)
    days = np.where(rng.random(500) < 0.3, rng.choice([-1.0, 2.0], 500, p=[0.55, 0.45]), 0.0)
    low = simulate(days, 0.25, RULES, runs=3000)
    high = simulate(days, 2.0, RULES, runs=3000)
    assert high.fail_daily + high.fail_total > low.fail_daily + low.fail_total
    assert low.unresolved > high.unresolved


def test_walk_forward_only_counts_unseen_periods():
    bars = trending(365 * 6, slope=0.1, seed=7)
    wf = walk_forward(bars, TrendBreakout, "X", train_years=3, test_years=1, min_trades=1)
    assert len(wf.folds) == 3
    first_test = wf.folds[0].test_start
    assert (wf.oos_trades["entry_time"] >= first_test).all()
    for f in wf.folds:
        assert set(f.params) == set(TrendBreakout.param_grid)


def hourly_day(date, range_hl=(101.0, 99.0), breakout_hour=None, breakout_close=103.0, later=None):
    """24 H1 bars: quiet range, optional breakout bar, then `later` (hour -> (o,h,l,c))."""
    rows = []
    for h in range(24):
        if h < 7:
            o = c = 100.0
            hi, lo = range_hl
        else:
            o = c = 100.0
            hi, lo = 100.5, 99.5
        rows.append([o, hi, lo, c])
    if breakout_hour is not None:
        rows[breakout_hour] = [100.0, breakout_close + 0.2, 100.0, breakout_close]
    for h, bar in (later or {}).items():
        rows[h] = list(bar)
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    df.insert(0, "time", pd.date_range(date, periods=24, freq="h", tz="UTC"))
    return df


def test_london_breakout_long_flat_by_evening():
    from trading_ai.strategies import SessionBreakout
    day1 = hourly_day("2024-03-04", breakout_hour=8, later={h: (103.0, 103.5, 102.5, 103.0) for h in range(9, 24)})
    [t] = run_backtest(day1, SessionBreakout(), "GOLD")
    assert t.direction == "long"
    assert t.entry_time == pd.Timestamp("2024-03-04 09:00", tz="UTC")
    assert t.stop_dist == pytest.approx(2.0)          # range 99..101
    assert t.exit_reason == "signal"
    assert t.exit_time == pd.Timestamp("2024-03-04 20:00", tz="UTC")


def test_london_breakout_only_first_signal_and_no_entry_after_window():
    from trading_ai.strategies import SessionBreakout
    s = SessionBreakout()
    day = hourly_day("2024-03-05", later={
        8: (100.0, 100.2, 97.8, 98.0),     # first break: short
        9: (98.0, 103.2, 98.0, 103.0),     # opposite break: ignored
        13: (100.0, 104.0, 100.0, 104.0),  # after entry window: ignored
    })
    sig = s.signals(day)
    assert sig["short_entry"].sum() == 1 and sig["long_entry"].sum() == 0


def test_london_breakout_skips_narrow_range_and_rejects_daily_bars():
    from trading_ai.strategies import SessionBreakout
    day = hourly_day("2024-03-06", range_hl=(100.01, 99.99), breakout_hour=8)
    assert not SessionBreakout().signals(day)[["long_entry", "short_entry"]].any().any()
    with pytest.raises(ValueError, match="H1"):
        SessionBreakout().signals(ohlc([FLAT] * 5))


def test_breakout_on_last_bar_of_day_is_not_carried_overnight():
    from trading_ai.strategies import SessionBreakout
    short_day = hourly_day("2024-03-07", breakout_hour=8).iloc[:9]   # data ends at the breakout bar
    next_day = hourly_day("2024-03-08")
    trades = run_backtest(pd.concat([short_day, next_day], ignore_index=True), SessionBreakout(), "GOLD")
    assert trades == []


def test_ny_breakout_uses_us_open_range():
    from trading_ai.strategies import NYBreakout
    rows = hourly_day("2024-03-04")
    rows.loc[13:14, ["high", "low"]] = [102.0, 98.0]
    rows.loc[16, ["open", "high", "low", "close"]] = [100.0, 103.2, 100.0, 103.0]
    sig = NYBreakout().signals(rows)
    assert sig.loc[16, "long_entry"] and sig["long_entry"].sum() == 1
    assert sig.loc[16, "stop_dist"] == pytest.approx(4.0)


def test_nights_held_counts_weekday_rollovers_with_triple_wednesday():
    from trading_ai.backtest.engine import nights_held
    ts = lambda s: pd.Timestamp(s, tz="UTC")
    assert nights_held(ts("2024-03-04 10:00"), ts("2024-03-04 20:00")) == 0   # same day
    assert nights_held(ts("2024-03-04 10:00"), ts("2024-03-05 10:00")) == 1   # Mon night
    assert nights_held(ts("2024-03-06 10:00"), ts("2024-03-07 10:00")) == 3   # Wed = triple
    assert nights_held(ts("2024-03-08 10:00"), ts("2024-03-11 10:00")) == 1   # Fri -> Mon
    assert nights_held(ts("2024-03-04 10:00"), ts("2024-03-11 10:00")) == 7   # full week


def test_swap_is_charged_in_r():
    bars = ohlc([FLAT, FLAT, FLAT, FLAT, FLAT], start="2024-03-04")  # Mon..Fri
    [t] = run_backtest(bars, Scripted(entries=[0], exits=[2]), "X", swap_long=-0.5)
    # entry Tue open, exit Thu open: Tue night (1) + Wed night (3) = 4 nights x -0.5 = -2.0
    assert t.swap_r == pytest.approx(-2.0 / 5)
    assert t.r == pytest.approx(t.gross_r - 0.4)


def test_swap_spec_conversion():
    from trading_ai.data.specs import swap_per_night, triple_swap_weekday
    points = {"swap_mode": 1, "swap_long": -300.0, "swap_short": 100.0, "point": 0.001}
    assert swap_per_night(points, 2000.0)[:2] == pytest.approx((-0.3, 0.1))
    money = {"swap_mode": 4, "swap_long": -5.0, "swap_short": 1.0, "trade_contract_size": 100.0,
             "currency_profit": "USD", "deposit_currency": "USD"}
    assert swap_per_night(money, 2000.0)[:2] == pytest.approx((-0.05, 0.01))
    interest = {"swap_mode": 5, "swap_long": -3.6, "swap_short": 0.0}
    assert swap_per_night(interest, 5000.0)[0] == pytest.approx(-0.5)
    assert swap_per_night({"swap_mode": 2, "swap_long": -1.0, "swap_short": 0.0}, 1.0)[2] is not None
    assert triple_swap_weekday({"swap_rollover3days": 3}) == 2   # MT5 Wednesday -> Python 2


def test_turn_of_month_holds_across_month_end():
    from trading_ai.strategies import TurnOfMonth
    days = pd.bdate_range("2024-01-02", "2024-03-29", tz="UTC")
    bars = pd.DataFrame({"time": days, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0})
    trades = run_backtest(bars, TurnOfMonth(entry_days_before=2, exit_day=3), "X")
    # Entry at the open of January's 2nd-to-last trading day (Jan 30), exit at the open of Feb's 4th (Feb 6)
    first = trades[0]
    assert first.entry_time == pd.Timestamp("2024-01-30", tz="UTC")
    assert first.exit_time == pd.Timestamp("2024-02-06", tz="UTC")
    assert first.exit_reason == "signal"
    assert len(trades) == 3 and trades[-1].exit_reason == "end"   # March's trade is still open when the data ends


def test_rsi2_both_goes_short_in_downtrends_only():
    from trading_ai.strategies import RSI2Both, RSI2Reversion
    rng = np.random.default_rng(8)
    close = 300 - 0.3 * np.arange(600) + rng.normal(0, 1.5, 600).cumsum() * 0.3
    bars = ohlc([(c, c + 1, c - 1, c) for c in close], start="2020-01-01")
    both = trades_frame(run_backtest(bars, RSI2Both(), "X"))
    assert (both["direction"] == "short").any()
    long_only = trades_frame(run_backtest(bars, RSI2Reversion(), "X"))
    assert (long_only["direction"] == "long").all()


def test_daily_r_correlation():
    from trading_ai.backtest.metrics import daily_r_correlation
    a = fake_trades([1.0, -1.0, 1.0, -1.0]).assign(strategy="a")
    b = fake_trades([1.0, -1.0, 1.0, -1.0]).assign(strategy="b")
    c = fake_trades([-1.0, 1.0, -1.0, 1.0]).assign(strategy="c")
    corr = daily_r_correlation(pd.concat([a, b, c]))
    assert corr.loc["a", "b"] == pytest.approx(1.0) and corr.loc["a", "c"] == pytest.approx(-1.0)
    assert daily_r_correlation(a).empty
