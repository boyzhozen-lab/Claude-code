"""Facts for daily/weekly reports and the watchdog, plus their plain-text (Lao) rendering.

All numbers come from here; the optional AI commentary only explains them.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from trading_ai.journal.stats import max_drawdown

STATE_TEXT = {
    "STATE_OK": "ປົກກະຕິ",
    "STATE_DAILY_LOCK": "ລັອກ: ເສຍເຖິງກຳນົດຂອງມື້",
    "STATE_TOTAL_LOCK": "ລັອກ: ເສຍລວມເຖິງກຳນົດ",
    "STATE_KILL": "Kill switch ເປີດຢູ່",
}


def trade_summary(trades: pd.DataFrame) -> dict[str, Any]:
    if trades.empty:
        return {"trades": 0}
    wins = trades[trades["net_profit"] > 0]
    return {
        "trades": len(trades),
        "wins": len(wins),
        "net_profit": round(float(trades["net_profit"].sum()), 2),
        "avg_r": round(float(trades["r_multiple"].dropna().mean()), 2) if trades["r_multiple"].notna().any() else None,
        "max_drawdown_money": round(max_drawdown(trades), 2),
    }


def build_facts(
    period: str,
    account: dict[str, Any],
    heartbeat: dict[str, Any] | None,
    heartbeat_age_min: float | None,
    kill_switch: bool,
    positions: list[dict[str, Any]],
    journal: pd.DataFrame,
    forward: dict[str, Any] | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    days = 1 if period == "daily" else 7
    since = pd.Timestamp(now) - pd.Timedelta(days=days)
    recent = journal[journal["close_time"] >= since] if not journal.empty else journal
    return {
        "period": period,
        "generated_utc": now.isoformat(timespec="minutes"),
        "account": {k: account.get(k) for k in ("login", "server", "currency", "balance", "equity")},
        "riskguard": {
            "state": heartbeat.get("state") if heartbeat else "NO_HEARTBEAT",
            "heartbeat_age_minutes": None if heartbeat_age_min is None else round(heartbeat_age_min, 1),
            "daily_pnl": heartbeat.get("daily_pnl") if heartbeat else None,
            "initial_balance": heartbeat.get("initial_balance") if heartbeat else None,
            "daily_limit_pct": heartbeat.get("daily_limit_pct") if heartbeat else None,
            "max_loss_pct": heartbeat.get("max_loss_pct") if heartbeat else None,
            "kill_switch": kill_switch,
        },
        "open_positions": positions,
        f"closed_last_{days}d": {
            "summary": trade_summary(recent),
            "by_strategy": {k: trade_summary(g) for k, g in recent.groupby("strategy_id")} if len(recent) else {},
            "trades": [
                {"strategy": r.strategy_id, "symbol": r.symbol, "direction": r.direction,
                 "closed": r.close_time.strftime("%Y-%m-%d %H:%M"), "exit": r.exit_reason,
                 "r": None if pd.isna(r.r_multiple) else round(r.r_multiple, 2), "profit": round(r.net_profit, 2)}
                for r in recent.itertuples()
            ],
        },
        "all_time": trade_summary(journal),
        "forward_check": forward,
    }


def render_plain(facts: dict[str, Any]) -> str:
    """Deterministic header with the key numbers, shown above any AI commentary."""
    acct, rg = facts["account"], facts["riskguard"]
    days = 1 if facts["period"] == "daily" else 7
    closed = facts[f"closed_last_{days}d"]["summary"]
    title = "📊 ລາຍງານປະຈຳວັນ" if facts["period"] == "daily" else "📊 ລາຍງານປະຈຳອາທິດ"
    lines = [
        f"{title} ({facts['generated_utc'][:10]})",
        f"ບັນຊີ {acct.get('login')}: balance {acct.get('balance')} / equity {acct.get('equity')} {acct.get('currency') or ''}",
        f"RiskGuard: {STATE_TEXT.get(rg['state'], rg['state'])}"
        + (f" (heartbeat {rg['heartbeat_age_minutes']} ນາທີກ່ອນ)" if rg["heartbeat_age_minutes"] is not None else ""),
        f"ອໍເດີເປີດຢູ່: {len(facts['open_positions'])}",
    ]
    for p in facts["open_positions"]:
        lines.append(f"  • {p['symbol']} {p['direction']} {p['volume']} lot, P/L {p['profit']:+.2f}")
    if closed.get("trades"):
        lines.append(f"ປິດແລ້ວ {days} ມື້ຜ່ານມາ: {closed['trades']} ໄມ້, ຊະນະ {closed['wins']}, ກຳໄລສຸດທິ {closed['net_profit']:+.2f}")
    else:
        lines.append(f"ປິດແລ້ວ {days} ມື້ຜ່ານມາ: ບໍ່ມີ")
    fc = facts.get("forward_check")
    if fc:
        lines.append(f"Forward check: ກົງກັນ {fc['matched']}, EA ພາດ {fc['missed_by_ea']}, ເກີນ {fc['extra_live']}, ຍັງເປີດ {fc['still_open']}")
    return "\n".join(lines)


def position_dict(p: dict[str, Any], to_internal) -> dict[str, Any]:
    return {
        "ticket": p.get("ticket"),
        "symbol": to_internal(p.get("symbol", "")),
        "direction": "long" if p.get("type") == 0 else "short",
        "volume": p.get("volume"),
        "open_price": p.get("price_open"),
        "sl": p.get("sl") or None,
        "profit": round(float(p.get("profit") or 0.0), 2),
        "magic": p.get("magic"),
    }
