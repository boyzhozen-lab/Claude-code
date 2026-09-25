import pytest

from conftest import Order, deal
from trading_ai.journal.importer import trades_from_history

T0 = 1_700_000_000  # 2023-11-14 22:13:20 UTC


def run(deals, orders=()):
    return trades_from_history(
        [d._asdict() for d in deals], [o._asdict() for o in orders],
        account="1", server_tz="UTC", to_internal=lambda s: {"XAUUSDm": "GOLD"}.get(s, s),
    )


def test_long_win_hits_tp_with_r_multiple():
    deals = [
        deal(1, 10, T0, 0, 0, 0.10, 2000.0, commission=-0.7),
        deal(2, 10, T0 + 3600, 1, 1, 0.10, 2020.0, profit=200.0, commission=-0.7, reason=5),
    ]
    orders = [Order(1, T0, T0 * 1000, 10, 1990.0, 2020.0, "XAUUSDm")]
    [t] = run(deals, orders).trades
    assert t.direction == "long"
    assert t.symbol == "GOLD" and t.broker_symbol == "XAUUSDm"
    assert t.sl == 1990.0 and t.tp == 2020.0
    assert t.r_multiple == pytest.approx(2.0)
    assert t.net_profit == pytest.approx(198.6)
    assert t.exit_reason == "tp"
    assert t.open_time == "2023-11-14T22:13:20+00:00"
    assert t.strategy_id == "manual"


def test_short_loss_with_partial_closes_and_magic():
    deals = [
        deal(1, 11, T0, 1, 0, 0.20, 2000.0, magic=7),
        deal(2, 11, T0 + 60, 0, 1, 0.10, 2005.0, profit=-50.0),
        deal(3, 11, T0 + 120, 0, 1, 0.10, 2010.0, profit=-100.0, reason=4),
    ]
    orders = [Order(1, T0, T0 * 1000, 11, 2010.0, 0.0, "XAUUSDm")]
    [t] = run(deals, orders).trades
    assert t.direction == "short"
    assert t.exit_price == pytest.approx(2007.5)
    assert t.r_multiple == pytest.approx(-0.75)
    assert t.tp is None
    assert t.exit_reason == "sl"
    assert t.strategy_id == "magic_7"


def test_open_and_partially_closed_positions_are_skipped():
    deals = [
        deal(1, 20, T0, 0, 0, 0.10, 2000.0),                     # still open
        deal(2, 21, T0, 0, 0, 0.20, 2000.0),
        deal(3, 21, T0 + 60, 1, 1, 0.10, 2001.0, profit=10.0),    # half closed
    ]
    result = run(deals)
    assert result.trades == [] and result.skipped_open == 2


def test_non_trade_deals_ignored_and_missing_sl_gives_no_r():
    balance = deal(1, 0, T0, 2, 0, 0.0, 0.0, profit=10000.0)
    deals = [balance, deal(2, 30, T0, 0, 0, 1.0, 1.1), deal(3, 30, T0 + 60, 1, 1, 1.0, 1.2, profit=5.0)]
    [t] = run(deals).trades
    assert t.r_multiple is None and t.sl is None


def test_netting_reversal_is_skipped():
    deals = [deal(1, 40, T0, 0, 0, 1.0, 1.1), deal(2, 40, T0 + 60, 1, 2, 2.0, 1.2)]
    assert run(deals).skipped_reversal == 1


def test_server_timezone_is_converted_to_utc():
    deals = [deal(1, 50, T0, 0, 0, 1.0, 1.1), deal(2, 50, T0 + 60, 1, 1, 1.0, 1.2)]
    result = trades_from_history([d._asdict() for d in deals], [], "1", "Europe/Athens", str)
    # 22:13 Athens wall clock in November (UTC+2) is 20:13 UTC.
    assert result.trades[0].open_time == "2023-11-14T20:13:20+00:00"
