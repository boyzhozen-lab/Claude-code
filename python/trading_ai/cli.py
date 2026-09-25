"""Command line entry point: `python -m trading_ai <command>`."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

from trading_ai.config import ConfigError, Settings, load_settings
from trading_ai.data import bars as barstore
from trading_ai.data.mt5_client import MT5Error, account_summary, ensure_symbol, fetch_history, fetch_rates, mt5_session
from trading_ai.journal.db import Journal
from trading_ai.journal.enrich import Enricher
from trading_ai.journal.importer import trades_from_history
from trading_ai.journal.stats import max_drawdown, summarize


def cmd_check(s: Settings, args: argparse.Namespace) -> int:
    with mt5_session(s.terminal_path) as mt5:
        acct = account_summary(mt5)
        print(f"Connected: login {acct['login']} on {acct['server']}")
        print(f"Balance {acct['balance']} {acct['currency']}  equity {acct['equity']}  leverage 1:{acct['leverage']}")
        failed = 0
        for internal, broker in s.symbols.items():
            try:
                info = ensure_symbol(mt5, broker)
                print(f"  OK       {internal:<8} {broker:<12} digits={info['digits']} spread={info['spread']}")
            except MT5Error as e:
                failed += 1
                print(f"  MISSING  {internal:<8} {broker:<12} {e}")
    if failed:
        print(f"\n{failed} symbol(s) missing: fix the names in config/settings.toml")
    return 1 if failed else 0


def cmd_fetch_bars(s: Settings, args: argparse.Namespace) -> int:
    symbols = args.symbols or list(s.symbols)
    timeframes = args.timeframes or s.timeframes
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=365 * (args.years or s.history_years))
    with mt5_session(s.terminal_path) as mt5:
        for internal in symbols:
            broker = s.broker_symbol(internal)
            for tf in timeframes:
                raw = fetch_rates(mt5, broker, tf, start, end)
                if raw.empty:
                    print(f"  {internal} {tf}: no data returned")
                    continue
                path = barstore.bars_path(s.bars_dir, internal, tf)
                df = barstore.save_bars(barstore.normalize_rates(raw, s.server_timezone), path)
                print(f"  {internal} {tf}: {len(df):>7} bars  {df['time'].iloc[0]:%Y-%m-%d} -> {df['time'].iloc[-1]:%Y-%m-%d}")
    print(f"Saved to {s.bars_dir}")
    return 0


def cmd_validate_bars(s: Settings, args: argparse.Namespace) -> int:
    files = sorted(s.bars_dir.glob("*.csv"))
    if not files:
        print("No bar files yet. Run: python -m trading_ai fetch-bars")
        return 1
    bad = 0
    for path in files:
        report = barstore.validate_bars(barstore.load_bars(path))
        status = "OK " if not report["problems"] else "WARN"
        bad += bool(report["problems"])
        span = f"{report['start']:%Y-%m-%d} -> {report['end']:%Y-%m-%d}" if report["rows"] else ""
        print(f"  {status} {path.stem:<14} {report['rows']:>7} bars  {span}")
        for p in report["problems"]:
            print(f"         - {p}")
    return 0 if not bad else 1


def _load_bars_for(s: Settings):
    def load(symbol: str, timeframe: str):
        path = barstore.bars_path(s.bars_dir, symbol, timeframe)
        return barstore.load_bars(path) if path.exists() else None
    return load


def _enrich_all(s: Settings, journal: Journal) -> int:
    trades = journal.trades_df()
    enricher = Enricher(_load_bars_for(s))
    for _, trade in trades.iterrows():
        journal.update_context(int(trade["id"]), enricher.context(trade))
    return len(trades)


def cmd_import_history(s: Settings, args: argparse.Namespace) -> int:
    start = datetime.now(timezone.utc) - timedelta(days=args.days)
    with mt5_session(s.terminal_path) as mt5:
        account = str(account_summary(mt5)["login"])
        deals, orders = fetch_history(mt5, start)
    result = trades_from_history(deals, orders, account, s.server_timezone, s.internal_symbol)
    with Journal(s.journal_db) as journal:
        added = journal.insert_trades(result.trades)
        enriched = _enrich_all(s, journal)
        total = journal.count()
    print(f"Closed positions found: {len(result.trades)}  new: {added}  journal total: {total}")
    if result.skipped_open:
        print(f"Skipped {result.skipped_open} open or partially closed position(s); they import once closed")
    if result.skipped_reversal:
        print(f"Skipped {result.skipped_reversal} netting reversal(s) (not supported)")
    print(f"Context updated for {enriched} trade(s)")
    return 0


def cmd_enrich(s: Settings, args: argparse.Namespace) -> int:
    with Journal(s.journal_db) as journal:
        n = _enrich_all(s, journal)
    print(f"Context updated for {n} trade(s)")
    return 0


def cmd_stats(s: Settings, args: argparse.Namespace) -> int:
    with Journal(s.journal_db) as journal:
        trades = journal.trades_df()
    if trades.empty:
        print("Journal is empty. Run: python -m trading_ai import-history")
        return 1
    with pd.option_context("display.float_format", "{:,.2f}".format, "display.width", 140):
        print(summarize(trades).to_string())
        print(f"\nMax drawdown: {max_drawdown(trades):,.2f}")
        for by in args.by:
            print(f"\nBy {by}:")
            print(summarize(trades, by).to_string())
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="trading_ai", description="Trading AI tools")
    p.add_argument("--config", help="path to settings.toml (default: config/settings.toml)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="test the MT5 connection and symbol names").set_defaults(func=cmd_check)

    fb = sub.add_parser("fetch-bars", help="download price history from MT5")
    fb.add_argument("--symbols", nargs="+", help="internal names, e.g. GOLD NAS100")
    fb.add_argument("--timeframes", nargs="+", help="e.g. M15 H1 D1")
    fb.add_argument("--years", type=int)
    fb.set_defaults(func=cmd_fetch_bars)

    sub.add_parser("validate-bars", help="check downloaded bars for gaps and bad data").set_defaults(func=cmd_validate_bars)

    ih = sub.add_parser("import-history", help="import closed trades from MT5 into the journal")
    ih.add_argument("--days", type=int, default=365)
    ih.set_defaults(func=cmd_import_history)

    sub.add_parser("enrich", help="recompute market context for journal trades").set_defaults(func=cmd_enrich)

    st = sub.add_parser("stats", help="performance summary of the journal")
    st.add_argument("--by", nargs="*", default=["symbol", "session"],
                    help="group by columns, e.g. strategy_id symbol session weekday trend_d1 exit_reason")
    st.set_defaults(func=cmd_stats)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings(args.config)
        return args.func(settings, args)
    except (ConfigError, MT5Error) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
