from conftest import Order, SymbolInfo, deal
from trading_ai.cli import main

T0 = 1_700_000_000


def test_check_reports_missing_symbols(fake_mt5, config_file, capsys):
    assert main(["--config", str(config_file), "check"]) == 0
    assert "OK       GOLD" in capsys.readouterr().out

    fake_mt5.symbols.clear()
    assert main(["--config", str(config_file), "check"]) == 1
    assert "MISSING  GOLD" in capsys.readouterr().out


def test_fetch_validate_import_and_stats(fake_mt5, config_file, capsys):
    cfg = ["--config", str(config_file)]
    assert main(cfg + ["fetch-bars", "--years", "1"]) == 0
    bars_dir = config_file.parent.parent / "data" / "bars"
    assert (bars_dir / "GOLD_H1.csv").exists() and (bars_dir / "GOLD_D1.csv").exists()
    assert main(cfg + ["validate-bars"]) == 0

    fake_mt5.deals = [
        deal(1, 10, T0, 0, 0, 0.1, 2000.0),
        deal(2, 10, T0 + 3600, 1, 1, 0.1, 2010.0, profit=100.0, reason=5),
    ]
    fake_mt5.orders = [Order(1, T0, T0 * 1000, 10, 1995.0, 2010.0, "XAUUSDm")]
    assert main(cfg + ["import-history", "--days", "30"]) == 0
    out = capsys.readouterr().out
    assert "new: 1" in out

    assert main(cfg + ["import-history"]) == 0
    assert "new: 0" in capsys.readouterr().out

    assert main(cfg + ["stats", "--by", "symbol", "exit_reason"]) == 0
    out = capsys.readouterr().out
    assert "GOLD" in out and "tp" in out


def test_stats_on_empty_journal(config_file, capsys):
    assert main(["--config", str(config_file), "stats"]) == 1


def test_missing_mt5_package_is_a_clean_error(config_file, capsys, monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "MetaTrader5", None)
    assert main(["--config", str(config_file), "check"]) == 2
    assert "MetaTrader5 package not installed" in capsys.readouterr().err


def test_unknown_symbol_is_a_clean_error(fake_mt5, config_file, capsys):
    assert main(["--config", str(config_file), "fetch-bars", "--symbols", "BTC"]) == 2
    assert "Unknown symbol 'BTC'" in capsys.readouterr().err


def test_backtest_and_challenge_commands(config_file, capsys):
    import numpy as np
    import pandas as pd
    from trading_ai.data.bars import save_bars

    rng = np.random.default_rng(11)
    n = 365 * 6
    close = 2000 + np.cumsum(rng.normal(0.3, 8, n))
    bars = pd.DataFrame({
        "time": pd.date_range("2019-01-01", periods=n, freq="D", tz="UTC"),
        "open": close, "high": close + 5, "low": close - 5, "close": close,
        "tick_volume": 1, "spread": 20,
    })
    save_bars(bars, config_file.parent.parent / "data" / "bars" / "GOLD_D1.csv")
    cfg = ["--config", str(config_file)]

    assert main(cfg + ["backtest", "--strategy", "trend_breakout", "rsi2_reversion"]) == 0
    out = capsys.readouterr().out
    assert "trend_breakout on GOLD" in out and "PORTFOLIO" in out and "no [costs] entry" in out
    assert (config_file.parent.parent / "reports" / "backtest_trend_breakout_rsi2_reversion.csv").exists()

    assert main(cfg + ["backtest", "--strategy", "trend_breakout", "--walk-forward"]) == 0
    assert "train" in capsys.readouterr().out

    code = main(cfg + ["challenge", "--strategy", "trend_breakout", "rsi2_reversion",
                       "--risks", "0.5", "1.0", "--runs", "500"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "P1 pass" in out and "0.50%" in out


def test_backtest_without_data(config_file, capsys):
    assert main(["--config", str(config_file), "backtest", "--strategy", "trend_breakout"]) == 1
    assert "run fetch-bars first" in capsys.readouterr().out


def test_mixed_daily_and_hourly_strategies(config_file, capsys):
    import numpy as np
    import pandas as pd
    from trading_ai.data.bars import save_bars

    rng = np.random.default_rng(4)
    bars_dir = config_file.parent.parent / "data" / "bars"
    for tf, freq, n, vol in (("D1", "D", 365 * 5, 8.0), ("H1", "h", 24 * 365 * 2, 1.5)):
        close = 2000 + np.cumsum(rng.normal(0, vol, n))
        save_bars(pd.DataFrame({
            "time": pd.date_range("2022-01-01", periods=n, freq=freq, tz="UTC"),
            "open": close, "high": close + vol, "low": close - vol, "close": close,
            "tick_volume": 1, "spread": 20,
        }), bars_dir / f"GOLD_{tf}.csv")

    cfg = ["--config", str(config_file)]
    assert main(cfg + ["backtest", "--strategy", "trend_breakout", "london_breakout", "--risk", "0.5"]) == 0
    out = capsys.readouterr().out
    assert "london_breakout on GOLD" in out and "trend_breakout on GOLD" in out and "PORTFOLIO" in out

    assert main(cfg + ["backtest", "--strategy", "london_breakout", "--timeframe", "D1"]) == 1
    assert "needs H1" in capsys.readouterr().out


def test_install_ea_kill_resume_and_status(fake_mt5, config_file, tmp_path, capsys):
    import json
    fake_mt5.data_path = str(tmp_path / "terminal_data")
    fake_mt5.install_path = str(tmp_path / "terminal_install")   # no metaeditor here
    cfg = ["--config", str(config_file)]

    assert main(cfg + ["install-ea", "--no-compile"]) == 0
    assert (tmp_path / "terminal_data" / "MQL5" / "Experts" / "TradingAI" / "RiskGuard.mq5").exists()

    assert main(cfg + ["install-ea"]) == 1
    assert "MetaEditor not found" in capsys.readouterr().out

    files = tmp_path / "terminal_data" / "MQL5" / "Files" / "trading_ai"
    assert main(cfg + ["guard-status"]) == 1
    assert main(cfg + ["kill"]) == 0
    assert (files / "kill_switch").exists()
    (files / "heartbeat.json").write_text(json.dumps({"state": "STATE_KILL", "equity": 9950.0}))
    capsys.readouterr()
    assert main(cfg + ["guard-status"]) == 0
    out = capsys.readouterr().out
    assert "STATE_KILL" in out and "kill switch        ON" in out
    assert main(cfg + ["resume"]) == 0
    assert not (files / "kill_switch").exists()


def test_fetch_saves_specs_skips_missing_and_backtest_charges_swap(fake_mt5, config_file, capsys):
    import json
    text = config_file.read_text().replace('GOLD = "XAUUSDm"', 'GOLD = "XAUUSDm"\nDAX = "DE40m"')
    config_file.write_text(text)
    cfg = ["--config", str(config_file)]
    assert main(cfg + ["fetch-bars", "--timeframes", "D1", "--years", "3"]) == 1   # DAX missing
    out = capsys.readouterr().out
    assert "DAX: skipped" in out and "GOLD D1" in out
    specs = json.loads((config_file.parent.parent / "data" / "symbols.json").read_text())
    assert specs["GOLD"]["swap_long"] == -300.0 and specs["GOLD"]["deposit_currency"] == "USD"

    assert main(cfg + ["backtest", "--strategy", "rsi2_reversion", "--symbols", "GOLD", "--timeframe", "D1"]) in (0, 1)
    assert "no swap rates" not in capsys.readouterr().out


def test_list_symbols(fake_mt5, config_file, capsys):
    assert main(["--config", str(config_file), "list-symbols", "metals"]) == 0
    out = capsys.readouterr().out
    assert "XAUUSDm" in out and "1 symbol(s)" in out
    assert main(["--config", str(config_file), "list-symbols", "indices"]) == 0
    assert "0 symbol(s)" in capsys.readouterr().out


def test_forward_check_runs_end_to_end(fake_mt5, config_file, capsys):
    import time
    from conftest import deal
    now = int(time.time())
    fake_mt5.deals = [deal(1, 70, now - 7200, 0, 0, 0.1, 2000.0, magic=2201),
                      deal(2, 70, now - 3600, 1, 1, 0.1, 2005.0, profit=50.0, magic=2201)]
    since = time.strftime("%Y-%m-%d", time.gmtime(now - 86400 * 3))
    cfg = ["--config", str(config_file)]
    assert main(cfg + ["fetch-bars", "--timeframes", "D1", "--years", "2"]) == 0
    assert main(cfg + ["forward-check", "--symbols", "GOLD", "--since", since]) == 0
    out = capsys.readouterr().out
    assert "extra_live" in out and "extra live 1" in out


def test_cost_check(config_file, capsys):
    import numpy as np
    import pandas as pd
    from trading_ai.data.bars import save_bars
    cfg_text = config_file.read_text() + '\n[costs]\nGOLD = 0.4\n'
    config_file.write_text(cfg_text)
    bars_dir = config_file.parent.parent / "data" / "bars"
    for tf, freq, rng_ in (("M5", "5min", 1.0), ("D1", "D", 20.0)):
        n = 500
        close = 2000 + np.zeros(n)
        save_bars(pd.DataFrame({"time": pd.date_range("2024-01-01", periods=n, freq=freq, tz="UTC"),
                                "open": close, "high": close + rng_ / 2, "low": close - rng_ / 2, "close": close,
                                "tick_volume": 1, "spread": 1}), bars_dir / f"GOLD_{tf}.csv")
    assert main(["--config", str(config_file), "cost-check"]) == 0
    out = capsys.readouterr().out
    assert "GOLD" in out and "M5" in out and "40" in out and "2" in out   # 0.4/1.0 = 40%, 0.4/20 = 2%
