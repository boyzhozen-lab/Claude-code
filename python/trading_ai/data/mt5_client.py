"""Thin wrapper around the MetaTrader5 Python package (Windows only).

The package attaches to an MT5 terminal that is running on the same machine,
so no login details are needed here: log in inside MT5 itself.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

import pandas as pd

# Keep each request small: MT5 silently truncates very large ranges.
_CHUNK = timedelta(days=180)


class MT5Error(RuntimeError):
    pass


def _import_mt5() -> Any:
    try:
        import MetaTrader5 as mt5  # type: ignore[import-not-found]
    except ImportError as e:
        raise MT5Error(
            "MetaTrader5 package not installed. It only works on Windows: "
            "pip install MetaTrader5"
        ) from e
    return mt5


@contextmanager
def mt5_session(terminal_path: str | None = None) -> Iterator[Any]:
    mt5 = _import_mt5()
    ok = mt5.initialize(terminal_path) if terminal_path else mt5.initialize()
    if not ok:
        raise MT5Error(
            f"Could not connect to MT5 ({mt5.last_error()}). "
            "Is the MT5 terminal open and logged in? "
            "Is 'Allow algorithmic trading' enabled in Tools > Options > Expert Advisors?"
        )
    try:
        yield mt5
    finally:
        mt5.shutdown()


def account_summary(mt5: Any) -> dict[str, Any]:
    info = mt5.account_info()
    if info is None:
        raise MT5Error(f"account_info failed: {mt5.last_error()}")
    a = info._asdict()
    return {k: a.get(k) for k in ("login", "server", "name", "currency", "balance", "equity", "leverage", "trade_mode")}


def ensure_symbol(mt5: Any, symbol: str) -> dict[str, Any]:
    """Make sure the symbol exists and is visible in Market Watch."""
    info = mt5.symbol_info(symbol)
    if info is None:
        raise MT5Error(f"Symbol '{symbol}' not found on this account. Check [symbols] in config/settings.toml")
    if not info.visible and not mt5.symbol_select(symbol, True):
        raise MT5Error(f"Could not add '{symbol}' to Market Watch: {mt5.last_error()}")
    return info._asdict()


def fetch_rates(mt5: Any, symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
    """Raw OHLC bars; `time` is broker-server time as Unix seconds."""
    tf = getattr(mt5, f"TIMEFRAME_{timeframe}", None)
    if tf is None:
        raise MT5Error(f"Unknown timeframe '{timeframe}'")
    ensure_symbol(mt5, symbol)

    frames = []
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + _CHUNK, end)
        rates = mt5.copy_rates_range(symbol, tf, chunk_start, chunk_end)
        if rates is not None and len(rates):
            frames.append(pd.DataFrame(rates))
        chunk_start = chunk_end
    if not frames:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"])
    return pd.concat(frames, ignore_index=True).drop_duplicates("time").sort_values("time", ignore_index=True)


def fetch_history(mt5: Any, start: datetime, end: datetime | None = None) -> tuple[list[dict], list[dict]]:
    """Closed-trade history as plain dicts: (deals, orders)."""
    end = end or datetime.now(timezone.utc) + timedelta(days=1)
    deals = mt5.history_deals_get(start, end)
    orders = mt5.history_orders_get(start, end)
    if deals is None or orders is None:
        raise MT5Error(f"Could not read trade history: {mt5.last_error()}")
    return [d._asdict() for d in deals], [o._asdict() for o in orders]
