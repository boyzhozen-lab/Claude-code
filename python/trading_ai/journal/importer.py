"""Turn MT5 deal/order history into one TradeRecord per closed position."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable

from trading_ai.journal.db import TradeRecord
from trading_ai.timeutil import server_ts_to_utc, to_iso

# MetaTrader5 constants (stable across package versions).
DEAL_TYPE_BUY, DEAL_TYPE_SELL = 0, 1
DEAL_ENTRY_IN, DEAL_ENTRY_OUT, DEAL_ENTRY_INOUT, DEAL_ENTRY_OUT_BY = 0, 1, 2, 3
EXIT_REASONS = {0: "manual", 1: "manual", 2: "manual", 3: "expert", 4: "sl", 5: "tp", 6: "stop_out"}

_VOLUME_EPS = 1e-9

# Magic numbers used by our EAs (mql5/Experts) -> strategy names in the journal.
KNOWN_MAGICS = {2201: "rsi2_reversion"}


@dataclass
class ImportResult:
    trades: list[TradeRecord]
    skipped_open: int = 0       # still open or partially closed
    skipped_reversal: int = 0   # netting-account reversals (not supported yet)


def _deal_ts(d: dict) -> float:
    msc = d.get("time_msc")
    return msc / 1000 if msc else d["time"]


def _vwap(deals: list[dict]) -> float:
    vol = sum(d["volume"] for d in deals)
    return sum(d["price"] * d["volume"] for d in deals) / vol


def _initial_sl_tp(orders: list[dict]) -> tuple[float | None, float | None]:
    """SL/TP from the order that opened the position (the initial risk)."""
    if not orders:
        return None, None
    first = min(orders, key=lambda o: (o.get("time_setup_msc") or o.get("time_setup", 0), o.get("ticket", 0)))
    return (first.get("sl") or None), (first.get("tp") or None)


def trades_from_history(
    deals: list[dict],
    orders: list[dict],
    account: str,
    server_tz: str,
    to_internal: Callable[[str], str],
    source: str = "mt5_history",
) -> ImportResult:
    by_position: dict[int, list[dict]] = defaultdict(list)
    for d in deals:
        if d.get("type") in (DEAL_TYPE_BUY, DEAL_TYPE_SELL) and d.get("position_id"):
            by_position[d["position_id"]].append(d)
    orders_by_position: dict[int, list[dict]] = defaultdict(list)
    for o in orders:
        if o.get("position_id"):
            orders_by_position[o["position_id"]].append(o)

    result = ImportResult(trades=[])
    for pid, pdeals in sorted(by_position.items()):
        pdeals.sort(key=_deal_ts)
        if any(d["entry"] == DEAL_ENTRY_INOUT for d in pdeals):
            result.skipped_reversal += 1
            continue
        ins = [d for d in pdeals if d["entry"] == DEAL_ENTRY_IN]
        outs = [d for d in pdeals if d["entry"] in (DEAL_ENTRY_OUT, DEAL_ENTRY_OUT_BY)]
        if not ins or not outs or abs(sum(d["volume"] for d in ins) - sum(d["volume"] for d in outs)) > _VOLUME_EPS:
            result.skipped_open += 1
            continue

        direction = "long" if ins[0]["type"] == DEAL_TYPE_BUY else "short"
        sign = 1 if direction == "long" else -1
        entry, exit_ = _vwap(ins), _vwap(outs)
        sl, tp = _initial_sl_tp(orders_by_position.get(pid, []))
        risk = abs(entry - sl) if sl else 0.0

        gross = sum(d.get("profit", 0.0) for d in pdeals)
        commission = sum(d.get("commission", 0.0) for d in pdeals)
        swap = sum(d.get("swap", 0.0) for d in pdeals)
        fee = sum(d.get("fee", 0.0) for d in pdeals)
        magic = ins[0].get("magic") or 0

        result.trades.append(TradeRecord(
            source=source,
            account=account,
            position_id=pid,
            strategy_id="manual" if magic == 0 else KNOWN_MAGICS.get(magic, f"magic_{magic}"),
            magic=magic,
            symbol=to_internal(ins[0]["symbol"]),
            broker_symbol=ins[0]["symbol"],
            direction=direction,
            volume=sum(d["volume"] for d in ins),
            open_time=to_iso(server_ts_to_utc(_deal_ts(ins[0]), server_tz)),
            close_time=to_iso(server_ts_to_utc(_deal_ts(outs[-1]), server_tz)),
            entry_price=entry,
            exit_price=exit_,
            sl=sl,
            tp=tp,
            gross_profit=gross,
            commission=commission,
            swap=swap,
            fee=fee,
            net_profit=gross + commission + swap + fee,
            r_multiple=sign * (exit_ - entry) / risk if risk else None,
            exit_reason=EXIT_REASONS.get(outs[-1].get("reason"), "other"),
            comment=ins[0].get("comment") or None,
        ))
    return result
