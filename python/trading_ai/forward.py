"""Forward-test check: did the live EA do what the backtest says it should?

Matches each backtest trade to a closed live trade on the same symbol and
direction entered within `tolerance_days`, and reports:
- matched trades, with entry slippage and exit differences in R
- backtest trades the EA missed
- live trades the backtest would not have taken (bugs or manual trades)
"""

from __future__ import annotations

import pandas as pd

STATUS_ORDER = ["matched", "missed_by_ea", "extra_live", "still_open"]


def compare_trades(backtest: pd.DataFrame, live: pd.DataFrame, tolerance_days: int = 1) -> pd.DataFrame:
    tol = pd.Timedelta(days=tolerance_days)
    used: set[int] = set()
    rows = []
    for _, bt in backtest.sort_values("entry_time").iterrows():
        if bt["exit_reason"] == "end":
            rows.append({"status": "still_open", "symbol": bt["symbol"], "direction": bt["direction"],
                         "bt_entry_time": bt["entry_time"], "bt_entry": bt["entry_price"]})
            continue
        candidates = live[
            (live["symbol"] == bt["symbol"]) & (live["direction"] == bt["direction"])
            & ((live["open_time"] - bt["entry_time"]).abs() <= tol) & ~live.index.isin(used)
        ]
        row = {"symbol": bt["symbol"], "direction": bt["direction"], "bt_entry_time": bt["entry_time"],
               "bt_entry": bt["entry_price"], "bt_exit_time": bt["exit_time"], "bt_exit_reason": bt["exit_reason"],
               "bt_r": bt["gross_r"]}
        if candidates.empty:
            rows.append({"status": "missed_by_ea", **row})
            continue
        lv = candidates.loc[(candidates["open_time"] - bt["entry_time"]).abs().idxmin()]
        used.add(lv.name)
        sign = 1 if bt["direction"] == "long" else -1
        rows.append({
            "status": "matched", **row,
            "live_entry_time": lv["open_time"], "live_entry": lv["entry_price"],
            "live_exit_time": lv["close_time"], "live_exit_reason": lv["exit_reason"],
            # positive = the live fill was worse than the backtest's
            "entry_slip_r": sign * (lv["entry_price"] - bt["entry_price"]) / bt["stop_dist"],
            "live_r": sign * (lv["exit_price"] - lv["entry_price"]) / bt["stop_dist"],
            "live_profit": lv["net_profit"],
        })
    for idx, lv in live.iterrows():
        if idx not in used:
            rows.append({"status": "extra_live", "symbol": lv["symbol"], "direction": lv["direction"],
                         "live_entry_time": lv["open_time"], "live_entry": lv["entry_price"],
                         "live_exit_time": lv["close_time"], "live_exit_reason": lv["exit_reason"],
                         "live_profit": lv["net_profit"]})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["status"] = pd.Categorical(out["status"], STATUS_ORDER, ordered=True)
    return out.sort_values(["status", "symbol"], ignore_index=True)


def summarize_check(cmp: pd.DataFrame) -> dict[str, float]:
    counts = cmp["status"].value_counts() if not cmp.empty else pd.Series(dtype=int)
    matched = cmp[cmp["status"] == "matched"] if not cmp.empty else cmp
    return {
        "matched": int(counts.get("matched", 0)),
        "missed_by_ea": int(counts.get("missed_by_ea", 0)),
        "extra_live": int(counts.get("extra_live", 0)),
        "still_open": int(counts.get("still_open", 0)),
        "avg_entry_slip_r": float(matched["entry_slip_r"].mean()) if len(matched) else float("nan"),
        "bt_r_matched": float(matched["bt_r"].sum()) if len(matched) else 0.0,
        "live_r_matched": float(matched["live_r"].sum()) if len(matched) else 0.0,
        "same_exit_day": int((matched["bt_exit_time"].dt.date == matched["live_exit_time"].dt.date).sum()) if len(matched) else 0,
    }
