from __future__ import annotations

import sys
import types
from collections import namedtuple
from pathlib import Path

import numpy as np
import pytest

SymbolInfo = namedtuple("SymbolInfo", "name visible digits spread")
AccountInfo = namedtuple("AccountInfo", "login server name currency balance equity leverage trade_mode")
Deal = namedtuple("Deal", "ticket order time time_msc type entry magic position_id reason volume price commission swap profit fee symbol comment")
Order = namedtuple("Order", "ticket time_setup time_setup_msc position_id sl tp symbol")


def deal(ticket, pos, t, type_, entry, volume, price, profit=0.0, commission=0.0, swap=0.0,
         reason=0, magic=0, symbol="XAUUSDm", comment=""):
    return Deal(ticket, ticket, t, t * 1000, type_, entry, magic, pos, reason, volume, price,
                commission, swap, profit, 0.0, symbol, comment)


class FakeMT5(types.ModuleType):
    TIMEFRAME_M15, TIMEFRAME_H1, TIMEFRAME_D1 = 15, 16385, 16408

    def __init__(self):
        super().__init__("MetaTrader5")
        self.symbols = {"XAUUSDm": SymbolInfo("XAUUSDm", True, 3, 16)}
        self.deals: list[Deal] = []
        self.orders: list[Order] = []
        self.connected = False

    def initialize(self, *a, **k):
        self.connected = True
        return True

    def shutdown(self):
        self.connected = False

    def last_error(self):
        return (1, "fake")

    def account_info(self):
        return AccountInfo(123456, "Exness-MT5Trial", "Demo", "USD", 10000.0, 10000.0, 100, 0)

    def symbol_info(self, name):
        return self.symbols.get(name)

    def symbol_select(self, name, enable):
        return True

    def copy_rates_range(self, symbol, tf, start, end):
        step = {15: 900, 16385: 3600, 16408: 86400}[tf]
        t0, t1 = int(start.timestamp()) // step * step, int(end.timestamp())
        times = np.arange(t0, t1, step)
        if not len(times):
            return None
        dtype = [("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"),
                 ("tick_volume", "i8"), ("spread", "i4"), ("real_volume", "i8")]
        rates = np.zeros(len(times), dtype=dtype)
        rates["time"] = times
        rates["open"] = rates["close"] = 2000.0
        rates["high"], rates["low"] = 2001.0, 1999.0
        return rates

    def history_deals_get(self, start, end):
        return tuple(self.deals)

    def history_orders_get(self, start, end):
        return tuple(self.orders)


@pytest.fixture
def fake_mt5(monkeypatch):
    fake = FakeMT5()
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
    return fake


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / "config" / "settings.toml"
    cfg.parent.mkdir()
    cfg.write_text(
        '[broker]\nname = "exness"\nserver_timezone = "UTC"\n\n'
        '[symbols]\nGOLD = "XAUUSDm"\n\n'
        '[download]\ntimeframes = ["H1", "D1"]\nyears = 1\n\n'
        '[paths]\ndata_dir = "data"\njournal_db = "data/journal.db"\n'
    )
    return cfg
