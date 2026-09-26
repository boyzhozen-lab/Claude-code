import pandas as pd
import pytest

from trading_ai.forward import compare_trades, summarize_check

ts = lambda s: pd.Timestamp(s, tz="UTC")


def bt(symbol, entry, exit_, entry_px, exit_px, reason="signal", direction="long", dist=10.0):
    sign = 1 if direction == "long" else -1
    return {"symbol": symbol, "direction": direction, "entry_time": ts(entry), "exit_time": ts(exit_),
            "entry_price": entry_px, "exit_price": exit_px, "stop_dist": dist, "exit_reason": reason,
            "gross_r": sign * (exit_px - entry_px) / dist}


def live(symbol, open_, close, entry_px, exit_px, direction="long", profit=0.0):
    return {"symbol": symbol, "direction": direction, "open_time": ts(open_), "close_time": ts(close),
            "entry_price": entry_px, "exit_price": exit_px, "exit_reason": "expert", "net_profit": profit}


def test_matching_missed_extra_and_open():
    backtest = pd.DataFrame([
        bt("SPX500", "2026-09-29 00:00", "2026-10-02 00:00", 100.0, 105.0),
        bt("NAS100", "2026-09-30 00:00", "2026-10-01 00:00", 200.0, 198.0),     # EA missed this
        bt("DOW30", "2026-10-05 00:00", "2026-10-06 00:00", 300.0, 301.0, reason="end"),
    ])
    lv = pd.DataFrame([
        live("SPX500", "2026-09-29 00:03", "2026-10-02 00:02", 100.5, 104.0, profit=35.0),
        live("SPX500", "2026-10-07 10:00", "2026-10-07 12:00", 110.0, 111.0),   # not a backtest trade
    ])
    cmp = compare_trades(backtest, lv)
    assert list(cmp["status"]) == ["matched", "missed_by_ea", "extra_live", "still_open"]
    m = cmp.iloc[0]
    assert m["entry_slip_r"] == pytest.approx(0.05)
    assert m["live_r"] == pytest.approx(0.35) and m["bt_r"] == pytest.approx(0.5)
    sm = summarize_check(cmp)
    assert (sm["matched"], sm["missed_by_ea"], sm["extra_live"], sm["still_open"]) == (1, 1, 1, 1)
    assert sm["same_exit_day"] == 1


def test_short_slippage_sign_and_empty():
    backtest = pd.DataFrame([bt("GOLD", "2026-09-29", "2026-09-30", 2000.0, 1990.0, direction="short")])
    lv = pd.DataFrame([live("GOLD", "2026-09-29 00:01", "2026-09-30 00:01", 1999.0, 1991.0, direction="short")])
    cmp = compare_trades(backtest, lv)
    assert cmp.iloc[0]["entry_slip_r"] == pytest.approx(0.1)    # sold 1.0 lower = worse
    empty_live = pd.DataFrame(columns=["symbol", "direction", "open_time", "close_time", "entry_price",
                                       "exit_price", "exit_reason", "net_profit"])
    assert compare_trades(backtest.iloc[0:0], empty_live).empty
