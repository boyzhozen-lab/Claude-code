"""Command line entry point: `python -m trading_ai <command>`."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

from trading_ai.backtest.challenge import simulate
from trading_ai.backtest.engine import run_backtest, trades_frame
from trading_ai.backtest.metrics import daily_r, performance
from trading_ai.backtest.walkforward import walk_forward
from trading_ai.config import ConfigError, Settings, load_settings
from trading_ai.data import bars as barstore
from trading_ai.data.mt5_client import MT5Error, account_summary, ensure_symbol, fetch_history, fetch_rates, mt5_session
from trading_ai.journal.db import Journal
from trading_ai.journal.enrich import Enricher
from trading_ai.journal.importer import trades_from_history
from trading_ai.journal.stats import max_drawdown, summarize
from trading_ai.strategies import STRATEGIES, get_strategy


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


def _collect_backtest_trades(s: Settings, args: argparse.Namespace) -> pd.DataFrame:
    """Run every strategy on every symbol; return all trades (walk-forward OOS if asked)."""
    parts = []
    for name in args.strategy:
        cls = get_strategy(name)
        timeframe = args.timeframe or cls.default_timeframe
        symbols = args.symbols or [x for x in cls.default_symbols if x in s.symbols] or list(s.symbols)
        for internal in symbols:
            s.broker_symbol(internal)  # validates the name
            path = barstore.bars_path(s.bars_dir, internal, timeframe)
            if not path.exists():
                print(f"  {name} {internal}: no {timeframe} data, run fetch-bars first")
                continue
            bars = barstore.load_bars(path)
            cost = s.costs.get(internal)
            if cost is None:
                print(f"  warning: no [costs] entry for {internal}, assuming zero cost")
                cost = 0.0
            if args.walk_forward:
                try:
                    wf = walk_forward(bars, cls, internal, cost)
                except ValueError as e:
                    print(f"  {name} {internal}: {e}")
                    continue
                for f in wf.folds:
                    params = ", ".join(f"{k}={v}" for k, v in f.params.items())
                    print(f"  {name} {internal} test {f.test_start:%Y-%m-%d}->{f.test_end:%Y-%m-%d}: "
                          f"[{params}] train {f.train_r:+.1f}R  test {f.test_r:+.1f}R ({f.test_trades} trades)")
                trades = wf.oos_trades
            else:
                try:
                    trades = trades_frame(run_backtest(bars, cls(), internal, cost))
                except ValueError as e:
                    print(f"  {name} {internal}: {e}")
                    continue
            parts.append(trades)
    if not parts:
        return trades_frame([])
    return pd.concat(parts, ignore_index=True).sort_values("exit_time", ignore_index=True)


PERF_FORMAT = {
    "trades": "{:.0f}", "trades_per_year": "{:.1f}", "win_rate": "{:.0%}", "avg_r": "{:+.2f}",
    "profit_factor": "{:.2f}", "total_r": "{:+.1f}", "return_pct": "{:+.1f}%",
    "return_pct_per_year": "{:+.1f}%", "max_dd_pct": "{:.1f}%", "worst_day_pct": "{:+.1f}%",
    "losing_streak": "{:.0f}", "years": "{:.1f}",
}


def _print_performance(title: str, trades: pd.DataFrame, risk: float) -> None:
    perf = performance(trades, risk)
    print(f"\n{title}")
    if not perf["trades"]:
        print("  no trades")
        return
    for key, fmt in PERF_FORMAT.items():
        print(f"  {key:<20} {fmt.format(perf[key])}")


def cmd_backtest(s: Settings, args: argparse.Namespace) -> int:
    trades = _collect_backtest_trades(s, args)
    if trades.empty:
        print("No trades.")
        return 1
    print(f"\nRisk per trade: {args.risk}% of initial balance. Swap/financing costs are NOT included.")
    for (strategy, symbol), group in trades.groupby(["strategy", "symbol"]):
        _print_performance(f"{strategy} on {symbol}", group, args.risk)
    if trades.groupby(["strategy", "symbol"]).ngroups > 1:
        _print_performance("PORTFOLIO (all combined)", trades, args.risk)
    reports = s.project_root / "reports"
    reports.mkdir(exist_ok=True)
    out = reports / f"backtest_{'_'.join(args.strategy)}{'_' + args.timeframe if args.timeframe else ''}{'_wf' if args.walk_forward else ''}.csv"
    trades.to_csv(out, index=False)
    print(f"\nTrades saved to {out}")
    return 0


def cmd_challenge(s: Settings, args: argparse.Namespace) -> int:
    trades = _collect_backtest_trades(s, args)
    if len(trades) < 30:
        print(f"Only {len(trades)} trades: too few for a meaningful simulation.")
        return 1
    days = daily_r(trades).to_numpy()
    p1, p2 = s.challenge["phase1"], s.challenge["phase2"]
    print(f"\n{len(trades)} trades over {len(days)} trading days, {args.runs} simulated challenges per row.")
    print(f"Phase 1: +{p1.profit_target}% target, -{p1.max_daily_loss}%/day, -{p1.max_total_loss}% total. "
          f"Phase 2: +{p2.profit_target}% target.\n")
    print(f"{'risk/trade':>10} {'P1 pass':>8} {'daily fail':>10} {'total fail':>10} {'no result':>9} "
          f"{'median days':>11} {'P2 pass':>8} {'both':>6}")
    for risk in args.risks:
        r1 = simulate(days, risk, p1, runs=args.runs, seed=args.seed)
        r2 = simulate(days, risk, p2, runs=args.runs, seed=args.seed + 1)
        print(f"{risk:>9.2f}% {r1.pass_rate:>8.0%} {r1.fail_daily:>10.0%} {r1.fail_total:>10.0%} "
              f"{r1.unresolved:>9.0%} {r1.median_days:>11.0f} {r2.pass_rate:>8.0%} {r1.pass_rate * r2.pass_rate:>6.0%}")
    print("\n'no result' = neither passed nor failed within ~1 year of trading days.")
    print("Rules are checked on closed daily P&L; real intraday floating losses make it harder.")
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

    def add_backtest_args(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--strategy", nargs="+", required=True, choices=list(STRATEGIES))
        sp.add_argument("--symbols", nargs="+", help="internal names; default: each strategy's own list")
        sp.add_argument("--timeframe", help="default: each strategy's own (D1 or H1)")
        sp.add_argument("--walk-forward", action="store_true",
                        help="only count trades from periods not used to choose parameters")

    bt = sub.add_parser("backtest", help="test strategies on downloaded history")
    add_backtest_args(bt)
    bt.add_argument("--risk", type=float, default=0.5, help="%% of balance risked per trade")
    bt.set_defaults(func=cmd_backtest)

    ch = sub.add_parser("challenge", help="simulate prop-firm challenges from backtest results")
    add_backtest_args(ch)
    ch.add_argument("--risks", nargs="+", type=float, default=[0.25, 0.5, 0.75, 1.0, 1.5])
    ch.add_argument("--runs", type=int, default=10_000)
    ch.add_argument("--seed", type=int, default=0)
    ch.set_defaults(func=cmd_challenge)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings(args.config)
        return args.func(settings, args)
    except (ConfigError, MT5Error) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
