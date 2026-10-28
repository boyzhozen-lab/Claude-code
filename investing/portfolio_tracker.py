#!/usr/bin/env python3
"""
$10,000 Core-Satellite portfolio tracker (yfinance).

Usage:
    pip install yfinance pandas
    python portfolio_tracker.py --init           # lock in shares at today's prices -> portfolio.json
    python portfolio_tracker.py                  # live report (value, P/L, daily return, stop alerts)
    python portfolio_tracker.py --fundamentals   # also print P/E, FCF, Debt/Equity for the stocks

After you actually buy, edit portfolio.json so "shares" and "cost_basis"
match your real fills (fractional shares are fine).
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

STARTING_CAPITAL = 10_000.00
PORTFOLIO_FILE = Path(__file__).with_name("portfolio.json")

# Target allocation: ticker -> (dollars, sleeve, hard stop vs cost basis)
TARGETS = {
    "VOO":  (4_000, "Core",      None),   # never stop out the core; rebalance instead
    "SCHD": (1_500, "Core",      None),
    "SMH":  (1_500, "Satellite", -0.25),
    "GOOGL": (1_200, "Satellite", -0.25),
    "MSFT": (1_000, "Satellite", -0.25),
    "SGOV": (  800, "Reserve",   None),   # T-bill ETF = dry powder for drawdowns
}
REBALANCE_BAND = 0.05  # flag when a position drifts >5 pts from target weight
TRAILING_STOP = -0.20  # satellite: -20% from 52-week high triggers a review


def fetch_prices(tickers):
    """Return DataFrame with last price, previous close and 52w high per ticker."""
    data = yf.download(tickers, period="1y", interval="1d",
                       auto_adjust=False, progress=False, group_by="ticker")
    rows = {}
    for t in tickers:
        closes = data[t]["Close"].dropna()
        if len(closes) < 2:
            sys.exit(f"Not enough price data for {t}")
        rows[t] = {
            "price": float(closes.iloc[-1]),
            "prev_close": float(closes.iloc[-2]),
            "high_52w": float(data[t]["High"].dropna().max()),
            "as_of": closes.index[-1].date().isoformat(),
        }
    # Use intraday price when the market is open
    for t in tickers:
        try:
            last = yf.Ticker(t).fast_info["last_price"]
            if last:
                rows[t]["price"] = float(last)
        except Exception:
            pass
    return pd.DataFrame(rows).T


def init_portfolio():
    tickers = list(TARGETS)
    px = fetch_prices(tickers)
    holdings = {}
    for t, (dollars, sleeve, stop) in TARGETS.items():
        price = px.loc[t, "price"]
        holdings[t] = {
            "shares": round(dollars / price, 6),
            "cost_basis": round(price, 4),
            "sleeve": sleeve,
            "stop_loss": stop,
        }
    payload = {
        "created": datetime.now().isoformat(timespec="seconds"),
        "starting_capital": STARTING_CAPITAL,
        "cash": 0.0,
        "holdings": holdings,
    }
    PORTFOLIO_FILE.write_text(json.dumps(payload, indent=2))
    print(f"Saved {PORTFOLIO_FILE} (edit shares/cost_basis to match real fills).")


def load_portfolio():
    if not PORTFOLIO_FILE.exists():
        sys.exit("No portfolio.json found. Run with --init first.")
    return json.loads(PORTFOLIO_FILE.read_text())


def report(show_fundamentals=False):
    pf = load_portfolio()
    holdings = pf["holdings"]
    tickers = list(holdings)
    px = fetch_prices(tickers)

    df = pd.DataFrame(holdings).T
    df[["shares", "cost_basis"]] = df[["shares", "cost_basis"]].astype(float)
    df = df.join(px.astype({"price": float, "prev_close": float, "high_52w": float}))
    df["value"] = df["shares"] * df["price"]
    df["cost"] = df["shares"] * df["cost_basis"]
    df["pl_$"] = df["value"] - df["cost"]
    df["pl_%"] = df["pl_$"] / df["cost"]
    df["day_$"] = df["shares"] * (df["price"] - df["prev_close"])
    df["day_%"] = df["price"] / df["prev_close"] - 1
    df["from_high"] = df["price"] / df["high_52w"] - 1

    cash = float(pf.get("cash", 0.0))
    total = df["value"].sum() + cash
    df["weight"] = df["value"] / total
    df["target_w"] = [TARGETS.get(t, (0,))[0] / STARTING_CAPITAL for t in df.index]

    prev_total = (df["shares"] * df["prev_close"]).sum() + cash
    day_ret = total / prev_total - 1
    total_ret = total / pf["starting_capital"] - 1

    print(f"\n=== $10K Core-Satellite Portfolio  |  {datetime.now():%Y-%m-%d %H:%M} ===")
    print(f"Prices as of: {df['as_of'].max()}\n")
    view = df[["sleeve", "shares", "cost_basis", "price", "value",
               "pl_$", "pl_%", "day_%", "weight", "target_w"]].copy()
    fmt = {
        "shares": "{:.4f}", "cost_basis": "${:,.2f}", "price": "${:,.2f}",
        "value": "${:,.2f}", "pl_$": "{:+,.2f}", "pl_%": "{:+.2%}",
        "day_%": "{:+.2%}", "weight": "{:.1%}", "target_w": "{:.1%}",
    }
    for col, f in fmt.items():
        view[col] = view[col].map(f.format)
    print(view.to_string())

    print("\n" + "-" * 60)
    print(f"Cash:                 ${cash:,.2f}")
    print(f"Total value:          ${total:,.2f}")
    print(f"Daily return:         {day_ret:+.2%}  (${total - prev_total:+,.2f})")
    print(f"Return since start:   {total_ret:+.2%}  (${total - pf['starting_capital']:+,.2f})")
    print("-" * 60)

    alerts = []
    for t, r in df.iterrows():
        stop = r["stop_loss"]
        if stop is not None and not pd.isna(stop) and r["pl_%"] <= float(stop):
            alerts.append(f"[HARD STOP] {t} is {r['pl_%']:+.1%} vs cost (limit {float(stop):.0%}) -> exit/trim")
        if r["sleeve"] == "Satellite" and r["from_high"] <= TRAILING_STOP:
            alerts.append(f"[TRAILING]  {t} is {r['from_high']:+.1%} from 52w high -> re-check thesis")
        drift = r["weight"] - r["target_w"]
        if abs(drift) > REBALANCE_BAND:
            alerts.append(f"[REBALANCE] {t} weight {r['weight']:.1%} vs target {r['target_w']:.1%}")
    satellite_w = df.loc[df["sleeve"] == "Satellite", "weight"].sum()
    if satellite_w > 0.45:
        alerts.append(f"[RISK]      Satellite sleeve at {satellite_w:.1%} (> 45% cap) -> trim to core")

    print("\nAlerts:" if alerts else "\nAlerts: none - stay the course.")
    for a in alerts:
        print("  " + a)

    if show_fundamentals:
        print_fundamentals([t for t in tickers if holdings[t]["sleeve"] == "Satellite"])


def print_fundamentals(tickers):
    print("\n=== Fundamentals (individual stocks only) ===")
    rows = []
    for t in tickers:
        info = yf.Ticker(t).info
        if info.get("quoteType", "EQUITY") != "EQUITY":
            continue  # ETFs have no single-company P/E / FCF / D/E
        fcf = info.get("freeCashflow")
        rows.append({
            "ticker": t,
            "trailing_PE": info.get("trailingPE"),
            "forward_PE": info.get("forwardPE"),
            "FCF_$B": fcf / 1e9 if fcf else None,
            "Debt/Equity": info.get("debtToEquity"),  # yfinance reports as % (e.g. 30 = 0.30x)
            "ROE": info.get("returnOnEquity"),
        })
    print(pd.DataFrame(rows).set_index("ticker").round(2).to_string())


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Track the $10K core-satellite portfolio.")
    p.add_argument("--init", action="store_true", help="create portfolio.json at current prices")
    p.add_argument("--fundamentals", action="store_true", help="print P/E, FCF, D/E for stocks")
    args = p.parse_args()
    if args.init:
        init_portfolio()
    report(show_fundamentals=args.fundamentals)
