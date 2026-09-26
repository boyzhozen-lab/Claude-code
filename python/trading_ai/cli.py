"""Command line entry point: `python -m trading_ai <command>`."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

from trading_ai.backtest.challenge import simulate
from trading_ai.backtest.engine import run_backtest, trades_frame
from trading_ai.backtest.metrics import daily_r, daily_r_correlation, performance
from trading_ai.backtest.orb import OrbParams, orb_backtest
from trading_ai.backtest.walkforward import walk_forward
from trading_ai.config import ConfigError, Settings, load_settings
from trading_ai.data import bars as barstore
from trading_ai.data import specs as symspecs
from trading_ai.data import terminal as term
from trading_ai.data.mt5_client import MT5Error, account_summary, ensure_symbol, fetch_history, fetch_rates, mt5_session
from trading_ai.journal.db import Journal
from trading_ai.journal.enrich import Enricher
from trading_ai.journal.importer import trades_from_history
from trading_ai.forward import compare_trades, summarize_check
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
    specs, missing = {}, []
    with mt5_session(s.terminal_path) as mt5:
        deposit = account_summary(mt5)["currency"]
        for internal in symbols:
            broker = s.broker_symbol(internal)
            try:
                specs[internal] = symspecs.spec_from_info(ensure_symbol(mt5, broker), deposit)
            except MT5Error as e:
                missing.append(internal)
                print(f"  {internal}: skipped, {e}")
                continue
            for tf in timeframes:
                years = args.years or (s.history_years_d1 if tf == "D1" else s.history_years)
                raw = fetch_rates(mt5, broker, tf, end - timedelta(days=round(365.25 * years)), end)
                if raw.empty:
                    print(f"  {internal} {tf}: no data returned")
                    continue
                path = barstore.bars_path(s.bars_dir, internal, tf)
                df = barstore.save_bars(barstore.normalize_rates(raw, s.server_timezone), path)
                print(f"  {internal} {tf}: {len(df):>7} bars  {df['time'].iloc[0]:%Y-%m-%d} -> {df['time'].iloc[-1]:%Y-%m-%d}")
    symspecs.save_specs(s.specs_path, specs)
    print(f"Saved to {s.bars_dir} (symbol specs incl. swap rates: {s.specs_path.name})")
    return 1 if missing else 0


def cmd_list_symbols(s: Settings, args: argparse.Namespace) -> int:
    with mt5_session(s.terminal_path) as mt5:
        needle = args.pattern.lower()
        found = [i for i in (mt5.symbols_get() or ())
                 if needle in f"{i.name} {i.path} {i.description}".lower()]
        for info in sorted(found, key=lambda i: i.path):
            print(f"  {info.name:<16} {info.path:<40} {info.description}")
    print(f"{len(found)} symbol(s)")
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


def _swap_for(s: Settings, internal: str, price: float) -> tuple[float, float, int]:
    spec = symspecs.load_specs(s.specs_path).get(internal)
    if spec is None:
        print(f"  warning: no swap rates for {internal} (run fetch-bars), swap not charged")
        return 0.0, 0.0, 2
    long_, short_, warning = symspecs.swap_per_night(spec, price)
    if warning:
        print(f"  warning: {internal}: {warning}")
    return long_, short_, symspecs.triple_swap_weekday(spec)


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
            swap = _swap_for(s, internal, float(bars["close"].iloc[-1]))
            cost = s.costs.get(internal)
            if cost is None:
                print(f"  warning: no [costs] entry for {internal}, assuming zero cost")
                cost = 0.0
            if args.walk_forward:
                try:
                    wf = walk_forward(bars, cls, internal, cost, swap)
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
                    trades = trades_frame(run_backtest(bars, cls(), internal, cost, *swap))
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
    "losing_streak": "{:.0f}", "swap_r": "{:+.1f}R", "years": "{:.1f}",
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
    print(f"\nRisk per trade: {args.risk}% of initial balance. Costs and overnight swap included.")
    for (strategy, symbol), group in trades.groupby(["strategy", "symbol"]):
        _print_performance(f"{strategy} on {symbol}", group, args.risk)
    if trades.groupby(["strategy", "symbol"]).ngroups > 1:
        _print_performance("PORTFOLIO (all combined)", trades, args.risk)
    for name, group in trades.groupby("strategy"):
        if trades["strategy"].nunique() > 1 and group["symbol"].nunique() > 1:
            _print_performance(f"{name} (all its symbols)", group, args.risk)
    corr = daily_r_correlation(trades)
    if not corr.empty:
        print("\nCorrelation of daily results between strategies (near 0 = good diversification):")
        print(corr.round(2).to_string())
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


def cmd_install_ea(s: Settings, args: argparse.Namespace) -> int:
    with mt5_session(s.terminal_path) as mt5:
        paths = term.terminal_paths(mt5)
    installed = term.install_experts(paths)
    if not installed:
        print("No .mq5 files found in the mql5 folder")
        return 1
    failed = 0
    for mq5 in installed:
        print(f"Copied {mq5.name} -> {mq5.parent}")
        if args.no_compile:
            continue
        ok, log = term.compile_expert(paths, mq5)
        print(f"  compile: {'OK' if ok else 'FAILED'}")
        if not ok:
            failed += 1
            print(log)
    if not failed:
        print("\nIn MT5: Navigator (Ctrl+N) > Expert Advisors > TradingAI (right-click > Refresh if missing).")
    return 1 if failed else 0


def cmd_kill(s: Settings, args: argparse.Namespace) -> int:
    with mt5_session(s.terminal_path) as mt5:
        paths = term.terminal_paths(mt5)
    paths.files.mkdir(parents=True, exist_ok=True)
    paths.kill_switch.write_text("created by trading_ai kill\n")
    print("KILL SWITCH ON: RiskGuard will close all positions and block new ones within seconds.")
    print("Undo with: python -m trading_ai resume")
    return 0


def cmd_resume(s: Settings, args: argparse.Namespace) -> int:
    with mt5_session(s.terminal_path) as mt5:
        paths = term.terminal_paths(mt5)
    if paths.kill_switch.exists():
        paths.kill_switch.unlink()
        print("Kill switch removed. Trading allowed again (daily/max-loss locks still apply).")
    else:
        print("Kill switch was not on.")
    return 0


def cmd_guard_status(s: Settings, args: argparse.Namespace) -> int:
    with mt5_session(s.terminal_path) as mt5:
        paths = term.terminal_paths(mt5)
    hb = term.read_heartbeat(paths)
    if hb is None:
        print("No heartbeat yet: is RiskGuard attached to a chart with Algo Trading enabled?")
        return 1
    for key, value in hb.items():
        print(f"  {key:<18} {value}")
    if paths.kill_switch.exists():
        print("  kill switch        ON")
    return 0


def cmd_backtest_orb(s: Settings, args: argparse.Namespace) -> int:
    """USTEC_ORB_EA v1.6 rules on M5 history."""
    m5_path = barstore.bars_path(s.bars_dir, args.symbol, "M5")
    d1_path = barstore.bars_path(s.bars_dir, args.symbol, "D1")
    if not m5_path.exists():
        print(f"No M5 data for {args.symbol}. Run: python -m trading_ai fetch-bars --symbols {args.symbol} --timeframes M5 D1")
        return 1
    m5 = barstore.load_bars(m5_path)
    d1 = barstore.load_bars(d1_path) if d1_path.exists() else None
    spec = symspecs.load_specs(s.specs_path).get(args.symbol, {})
    point = float(spec.get("point") or 0.01)
    cost = s.costs.get(args.symbol, 0.0)
    variants = {"EA v1.6 as configured": OrbParams(point=point)}
    if args.compare:
        variants["EA v1.6, pessimistic trail (exit at 1R - trail)"] = OrbParams(point=point, trail_from_bar_high=False)
        variants["no trailing (BE only)"] = OrbParams(point=point, use_trail=False)
        variants["no trailing, no BE (SL/TP/11:00 only)"] = OrbParams(point=point, use_trail=False, be_rr=1e9)
    print(f"{args.symbol} M5 {m5['time'].iloc[0]:%Y-%m-%d} -> {m5['time'].iloc[-1]:%Y-%m-%d}, "
          f"point {point}, cost {cost} per trade, risk {args.risk}% per trade")
    last = None
    for title, params in variants.items():
        trades = trades_frame(orb_backtest(m5, d1, args.symbol, cost, params))
        _print_performance(title.upper(), trades, args.risk)
        if trades.empty:
            continue
        print("  exits: " + ", ".join(f"{k} {v}" for k, v in trades["exit_reason"].value_counts().items()))
        by_year = trades.groupby(trades["entry_time"].dt.year)["r"].agg(["count", "sum", "mean"])
        print("  by year:  " + "  ".join(f"{y}: {int(row['count'])}tr {row['sum']:+.1f}R" for y, row in by_year.iterrows()))
        last = last if last is not None else trades
    if last is not None and len(last) >= 30:
        days = daily_r(last).to_numpy()
        p1, p2 = s.challenge["phase1"], s.challenge["phase2"]
        print("\nChallenge simulation (EA as configured):")
        print(f"{'risk/trade':>10} {'P1 pass':>8} {'daily fail':>10} {'total fail':>10} {'no result':>9} {'median days':>11} {'both':>6}")
        for risk in (0.5, 1.0):
            r1 = simulate(days, risk, p1, runs=10_000)
            r2 = simulate(days, risk, p2, runs=10_000, seed=1)
            print(f"{risk:>9.2f}% {r1.pass_rate:>8.0%} {r1.fail_daily:>10.0%} {r1.fail_total:>10.0%} "
                  f"{r1.unresolved:>9.0%} {r1.median_days:>11.0f} {r1.pass_rate * r2.pass_rate:>6.0%}")
    print("\nNote: fixed EA parameters (not walk-forward). If they were tuned on this same period, results are optimistic.")
    return 0


def cmd_forward_check(s: Settings, args: argparse.Namespace) -> int:
    """Compare the EA's live trades with what the backtest would have done since --since."""
    cls = get_strategy(args.strategy)
    since = pd.Timestamp(args.since, tz="UTC")
    symbols = args.symbols or [x for x in cls.default_symbols if x in s.symbols]
    tf = cls.default_timeframe
    now = datetime.now(timezone.utc)
    with mt5_session(s.terminal_path) as mt5:
        account = str(account_summary(mt5)["login"])
        for internal in symbols:   # refresh recent bars so the backtest sees the same days
            raw = fetch_rates(mt5, s.broker_symbol(internal), tf, now - timedelta(days=60), now)
            if not raw.empty:
                barstore.save_bars(barstore.normalize_rates(raw, s.server_timezone),
                                   barstore.bars_path(s.bars_dir, internal, tf))
        deals, orders = fetch_history(mt5, (since - pd.Timedelta(days=2)).to_pydatetime())
    result = trades_from_history(deals, orders, account, s.server_timezone, s.internal_symbol)
    with Journal(s.journal_db) as journal:
        journal.insert_trades(result.trades)
        live = journal.trades_df()
    live = live[(live["strategy_id"] == cls.name) & (live["account"] == account)
                & (live["open_time"] >= since - pd.Timedelta(days=1))]

    parts = []
    for internal in symbols:
        path = barstore.bars_path(s.bars_dir, internal, tf)
        if not path.exists():
            print(f"  {internal}: no {tf} data")
            continue
        bars = barstore.load_bars(path)
        swap = _swap_for(s, internal, float(bars["close"].iloc[-1]))
        trades = trades_frame(run_backtest(bars, cls(), internal, s.costs.get(internal, 0.0), *swap))
        parts.append(trades[trades["entry_time"] >= since])
    backtest = pd.concat(parts, ignore_index=True) if parts else trades_frame([])

    cmp = compare_trades(backtest, live)
    print(f"\nForward check: {cls.name} on account {account} since {since:%Y-%m-%d}, symbols {', '.join(symbols)}")
    if cmp.empty:
        print("No backtest signals and no live trades yet. Normal early on: RSI2 trades about once a week.")
        return 0
    view = cmp.copy()
    for col in ("bt_entry_time", "live_entry_time", "bt_exit_time", "live_exit_time"):
        if col in view:
            view[col] = view[col].dt.strftime("%m-%d %H:%M")
    cols = [c for c in ("status", "symbol", "direction", "bt_entry_time", "live_entry_time", "entry_slip_r",
                        "bt_exit_time", "live_exit_time", "bt_exit_reason", "live_exit_reason", "bt_r", "live_r")
            if c in view]
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(view[cols].to_string(index=False, na_rep="-", float_format=lambda x: f"{x:+.2f}"))
    sm = summarize_check(cmp)
    print(f"\nmatched {sm['matched']}  missed by EA {sm['missed_by_ea']}  extra live {sm['extra_live']}  "
          f"still open {sm['still_open']}")
    if sm["matched"]:
        print(f"avg entry slippage {sm['avg_entry_slip_r']:+.3f}R (backtest assumes about +0.01R)  "
              f"same exit day {sm['same_exit_day']}/{sm['matched']}")
        print(f"R on matched trades: backtest {sm['bt_r_matched']:+.2f}  live {sm['live_r_matched']:+.2f}")
    if sm["missed_by_ea"] or sm["extra_live"]:
        print("CHECK: missed or extra trades mean the EA and the backtest disagree (EA off? MT5 closed? manual trades?)")
    out = s.project_root / "reports" / f"forward_check_{cls.name}.csv"
    out.parent.mkdir(exist_ok=True)
    cmp.to_csv(out, index=False)
    print(f"Details saved to {out}")
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

    ls = sub.add_parser("list-symbols", help="find broker symbols by name/group/description, e.g. list-symbols indices")
    ls.add_argument("pattern", nargs="?", default="")
    ls.set_defaults(func=cmd_list_symbols)

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

    fc = sub.add_parser("forward-check", help="compare the EA's live trades with the backtest")
    fc.add_argument("--strategy", default="rsi2_reversion", choices=list(STRATEGIES))
    fc.add_argument("--since", default="2026-09-28", help="forward test start date (YYYY-MM-DD)")
    fc.add_argument("--symbols", nargs="+")
    fc.set_defaults(func=cmd_forward_check)

    ob = sub.add_parser("backtest-orb", help="backtest USTEC_ORB_EA v1.6 rules on M5 data")
    ob.add_argument("--symbol", default="NAS100")
    ob.add_argument("--risk", type=float, default=1.0)
    ob.add_argument("--compare", action="store_true", help="also run without trailing / break-even")
    ob.set_defaults(func=cmd_backtest_orb)

    ie = sub.add_parser("install-ea", help="copy our EAs into MT5 and compile them")
    ie.add_argument("--no-compile", action="store_true")
    ie.set_defaults(func=cmd_install_ea)
    sub.add_parser("kill", help="emergency: RiskGuard closes everything and blocks trading").set_defaults(func=cmd_kill)
    sub.add_parser("resume", help="remove the kill switch").set_defaults(func=cmd_resume)
    sub.add_parser("guard-status", help="show RiskGuard's latest heartbeat").set_defaults(func=cmd_guard_status)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings(args.config)
        return args.func(settings, args)
    except (ConfigError, MT5Error) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
