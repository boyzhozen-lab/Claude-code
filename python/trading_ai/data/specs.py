"""Symbol specifications saved from MT5 (swap rates, point size, ...), so
backtests can charge overnight financing without MT5 running."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# MetaTrader5 ENUM_SYMBOL_SWAP_MODE
SWAP_DISABLED, SWAP_POINTS, SWAP_CURRENCY_DEPOSIT = 0, 1, 4
SWAP_INTEREST_CURRENT, SWAP_INTEREST_OPEN = 5, 6

SPEC_FIELDS = (
    "point", "digits", "trade_contract_size", "currency_profit",
    "swap_mode", "swap_long", "swap_short", "swap_rollover3days",
)


def spec_from_info(info: dict[str, Any], deposit_currency: str) -> dict[str, Any]:
    spec = {k: info.get(k) for k in SPEC_FIELDS}
    spec["deposit_currency"] = deposit_currency
    return spec


def load_specs(path: Path) -> dict[str, dict[str, Any]]:
    return json.loads(path.read_text()) if path.exists() else {}


def save_specs(path: Path, specs: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = load_specs(path) | specs
    path.write_text(json.dumps(merged, indent=2, sort_keys=True))


def swap_per_night(spec: dict[str, Any], price: float) -> tuple[float, float, str | None]:
    """(long, short) swap per night in PRICE units (positive = you receive),
    plus a warning when the swap mode cannot be converted."""
    mode = spec.get("swap_mode")
    sl, ss = float(spec.get("swap_long") or 0), float(spec.get("swap_short") or 0)
    if mode == SWAP_DISABLED or (sl == 0 and ss == 0):
        return 0.0, 0.0, None
    if mode == SWAP_POINTS:
        point = float(spec["point"])
        return sl * point, ss * point, None
    if mode == SWAP_CURRENCY_DEPOSIT and spec.get("currency_profit") == spec.get("deposit_currency"):
        size = float(spec["trade_contract_size"])
        return sl / size, ss / size, None
    if mode in (SWAP_INTEREST_CURRENT, SWAP_INTEREST_OPEN):
        return price * sl / 100 / 360, price * ss / 100 / 360, None
    return 0.0, 0.0, f"swap mode {mode} not supported, swap ignored"


def triple_swap_weekday(spec: dict[str, Any]) -> int:
    """Python weekday (Mon=0) on which 3 nights are charged; MT5 counts Sunday=0."""
    mt5_day = spec.get("swap_rollover3days")
    return (int(mt5_day) - 1) % 7 if mt5_day is not None else 2
