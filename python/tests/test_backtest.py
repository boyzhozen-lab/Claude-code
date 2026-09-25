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
