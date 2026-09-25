import pytest

from trading_ai.journal.db import Journal, TradeRecord
from trading_ai.journal.stats import max_drawdown, summarize


def rec(pid, profit, symbol="GOLD", open_time="2024-01-02T08:00:00+00:00", r=None):
    return TradeRecord(
        source="mt5_history", account="1", position_id=pid, strategy_id="manual", magic=0,
        symbol=symbol, broker_symbol="XAUUSDm", direction="long", volume=0.1,
        open_time=open_time, close_time=open_time.replace("08:", "09:"),
        entry_price=2000.0, exit_price=2001.0, sl=None, tp=None,
        gross_profit=profit, commission=0.0, swap=0.0, fee=0.0, net_profit=profit,
        r_multiple=r, exit_reason="manual", comment=None,
    )


def test_insert_is_idempotent_and_context_updates():
    with Journal(":memory:") as j:
        assert j.insert_trades([rec(1, 10.0), rec(2, -5.0)]) == 2
        assert j.insert_trades([rec(1, 10.0), rec(3, 1.0)]) == 1
        assert j.count() == 3
        tid = int(j.trades_df()["id"].iloc[0])
        j.update_context(tid, {"session": "london", "atr_ratio": 1.2})
        row = j.trades_df().set_index("id").loc[tid]
        assert row["session"] == "london" and row["atr_ratio"] == 1.2
        assert str(row["open_time"].tz) == "UTC"


def test_update_context_rejects_core_columns():
    with Journal(":memory:") as j:
        j.insert_trades([rec(1, 10.0)])
        with pytest.raises(ValueError):
            j.update_context(1, {"net_profit": 999})


def test_journal_file_is_created(tmp_path):
    path = tmp_path / "sub" / "journal.db"
    with Journal(path) as j:
        j.insert_trades([rec(1, 1.0)])
    with Journal(path) as j:
        assert j.count() == 1


def test_summary_and_drawdown():
    with Journal(":memory:") as j:
        j.insert_trades([
            rec(1, 100.0, r=1.0, open_time="2024-01-01T08:00:00+00:00"),
            rec(2, -50.0, r=-1.0, open_time="2024-01-02T08:00:00+00:00"),
            rec(3, -30.0, symbol="NAS100", open_time="2024-01-03T08:00:00+00:00"),
            rec(4, 40.0, symbol="NAS100", open_time="2024-01-04T08:00:00+00:00"),
        ])
        trades = j.trades_df()
    overall = summarize(trades).iloc[0]
    assert overall["trades"] == 4
    assert overall["win_rate"] == 0.5
    assert overall["profit_factor"] == pytest.approx(140 / 80)
    assert overall["avg_r"] == 0.0
    by_symbol = summarize(trades, "symbol")
    assert by_symbol.loc["GOLD", "net_profit"] == 50.0
    assert max_drawdown(trades) == 80.0
