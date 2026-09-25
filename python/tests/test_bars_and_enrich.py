import numpy as np
import pandas as pd
import pytest

from trading_ai.data.bars import load_bars, normalize_rates, save_bars, validate_bars
from trading_ai.indicators import atr
from trading_ai.journal.enrich import Enricher


def make_bars(start, periods, freq, base=100.0, step=0.0, spread=1.0):
    times = pd.date_range(start, periods=periods, freq=freq, tz="UTC")
    close = base + step * np.arange(periods)
    return pd.DataFrame({
        "time": times, "open": close, "high": close + spread, "low": close - spread,
        "close": close, "tick_volume": 1, "spread": 10,
    })


def test_normalize_converts_server_time_to_utc():
    raw = pd.DataFrame({"time": [1_700_000_000], "open": [1.0], "high": [2.0], "low": [0.5],
                        "close": [1.5], "tick_volume": [5], "spread": [3], "real_volume": [0]})
    utc = normalize_rates(raw, "UTC")
    athens = normalize_rates(raw, "Europe/Athens")
    assert utc["time"].iloc[0] - athens["time"].iloc[0] == pd.Timedelta(hours=2)
    assert "real_volume" not in utc.columns


def test_save_merges_and_dedupes(tmp_path):
    path = tmp_path / "GOLD_H1.csv"
    save_bars(make_bars("2024-01-01", 5, "h"), path)
    merged = save_bars(make_bars("2024-01-01 03:00", 5, "h", base=200.0), path)
    assert len(merged) == 8
    loaded = load_bars(path)
    assert loaded["time"].is_monotonic_increasing
    assert loaded.loc[loaded["time"] == pd.Timestamp("2024-01-01 03:00", tz="UTC"), "close"].item() == 200.0


def test_validate_flags_gaps_and_bad_ohlc():
    df = pd.concat([make_bars("2024-01-01", 3, "D"), make_bars("2024-01-20", 3, "D")], ignore_index=True)
    df.loc[1, "high"] = df.loc[1, "low"] - 1
    report = validate_bars(df)
    assert report["large_gaps"] == 1
    assert any("invalid OHLC" in p for p in report["problems"])
    assert validate_bars(make_bars("2024-01-01", 10, "D"))["problems"] == []


def test_atr_constant_range():
    df = make_bars("2024-01-01", 20, "h", spread=2.0)
    assert atr(df, 14).iloc[-1] == pytest.approx(4.0)


def trade(**kw):
    base = dict(symbol="GOLD", direction="long", entry_price=100.0, exit_price=103.0, sl=98.0,
                open_time=pd.Timestamp("2024-03-05 09:30", tz="UTC"),
                close_time=pd.Timestamp("2024-03-05 11:30", tz="UTC"))
    return pd.Series(base | kw)


def test_enrich_context_without_bars():
    ctx = Enricher(lambda s, tf: None).context(trade())
    assert ctx == {"session": "london", "weekday": "Tuesday", "duration_min": 120.0}


def test_enrich_trend_atr_and_excursions():
    bars = {
        "D1": make_bars("2023-01-01", 430, "D", step=0.5),                  # steady uptrend
        "H1": make_bars("2024-02-01", 24 * 40, "h", spread=1.0),
        "M15": make_bars("2024-03-05 09:00", 16, "15min", base=100.0, spread=0.0),
    }
    m15 = bars["M15"]
    m15.loc[m15["time"] == pd.Timestamp("2024-03-05 10:00", tz="UTC"), ["high", "low"]] = [105.0, 99.0]
    bars["M15"] = m15
    ctx = Enricher(lambda s, tf: bars.get(tf)).context(trade())
    assert ctx["trend_d1"] == "up"
    assert ctx["atr_ratio"] == pytest.approx(1.0)
    assert ctx["mfe_price"] == pytest.approx(5.0)
    assert ctx["mae_price"] == pytest.approx(1.0)
    assert ctx["mfe_r"] == pytest.approx(2.5) and ctx["mae_r"] == pytest.approx(0.5)


def test_enrich_ignores_bars_after_entry_for_indicators():
    # Only future D1 bars exist: there must be no trend reading (no look-ahead).
    bars = {"D1": make_bars("2024-03-06", 300, "D", step=1.0)}
    ctx = Enricher(lambda s, tf: bars.get(tf)).context(trade())
    assert "trend_d1" not in ctx
