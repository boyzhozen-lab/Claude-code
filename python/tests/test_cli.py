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
