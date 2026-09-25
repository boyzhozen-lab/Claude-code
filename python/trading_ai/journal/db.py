"""SQLite trade journal: one row per closed position, plus market context."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY,
    source          TEXT NOT NULL,      -- mt5_history | ea | backtest
    account         TEXT NOT NULL,
    position_id     INTEGER NOT NULL,
    strategy_id     TEXT NOT NULL,
    magic           INTEGER,
    symbol          TEXT NOT NULL,      -- internal name, e.g. GOLD
    broker_symbol   TEXT NOT NULL,
    direction       TEXT NOT NULL CHECK (direction IN ('long', 'short')),
    volume          REAL NOT NULL,
    open_time       TEXT NOT NULL,      -- ISO 8601, UTC
    close_time      TEXT NOT NULL,
    entry_price     REAL NOT NULL,
    exit_price      REAL NOT NULL,
    sl              REAL,               -- initial stop loss
    tp              REAL,
    gross_profit    REAL NOT NULL,
    commission      REAL NOT NULL DEFAULT 0,
    swap            REAL NOT NULL DEFAULT 0,
    fee             REAL NOT NULL DEFAULT 0,
    net_profit      REAL NOT NULL,
    r_multiple      REAL,               -- price move / initial risk, before costs
    exit_reason     TEXT,               -- sl | tp | manual | expert | stop_out | other
    comment         TEXT,

    -- market context (filled by `enrich`)
    session         TEXT,
    weekday         TEXT,
    duration_min    REAL,
    atr_ratio       REAL,               -- H1 ATR(14) / ATR(100) at entry
    trend_d1        TEXT,               -- up | down | mixed
    mae_price       REAL,               -- worst adverse move, price units
    mfe_price       REAL,               -- best favourable move, price units
    mae_r           REAL,
    mfe_r           REAL,

    -- filled by later phases
    spread_points   REAL,
    minutes_to_news REAL,
    daily_risk_score REAL,
    open_positions_at_entry INTEGER,
    day_pnl_at_entry REAL,
    ai_verdict      TEXT,
    ai_confidence   REAL,
    ai_reason       TEXT,

    imported_at     TEXT NOT NULL,
    UNIQUE (source, account, position_id)
);
CREATE INDEX IF NOT EXISTS idx_trades_open_time ON trades(open_time);
"""

CONTEXT_COLUMNS = frozenset({
    "session", "weekday", "duration_min", "atr_ratio", "trend_d1",
    "mae_price", "mfe_price", "mae_r", "mfe_r",
    "spread_points", "minutes_to_news", "daily_risk_score",
    "open_positions_at_entry", "day_pnl_at_entry",
    "ai_verdict", "ai_confidence", "ai_reason",
})


@dataclass
class TradeRecord:
    source: str
    account: str
    position_id: int
    strategy_id: str
    magic: int | None
    symbol: str
    broker_symbol: str
    direction: str
    volume: float
    open_time: str
    close_time: str
    entry_price: float
    exit_price: float
    sl: float | None
    tp: float | None
    gross_profit: float
    commission: float
    swap: float
    fee: float
    net_profit: float
    r_multiple: float | None
    exit_reason: str | None
    comment: str | None


class Journal:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def __enter__(self) -> "Journal":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self.conn.close()

    def insert_trades(self, records: Iterable[TradeRecord]) -> int:
        """Insert new trades; ones already in the journal are left untouched."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        inserted = 0
        with self.conn:
            for rec in records:
                row = asdict(rec) | {"imported_at": now}
                cols = ", ".join(row)
                marks = ", ".join(f":{c}" for c in row)
                cur = self.conn.execute(f"INSERT OR IGNORE INTO trades ({cols}) VALUES ({marks})", row)
                inserted += cur.rowcount
        return inserted

    def update_context(self, trade_id: int, fields: dict[str, object]) -> None:
        unknown = set(fields) - CONTEXT_COLUMNS
        if unknown:
            raise ValueError(f"Not context columns: {sorted(unknown)}")
        if not fields:
            return
        sets = ", ".join(f"{c} = :{c}" for c in fields)
        with self.conn:
            self.conn.execute(f"UPDATE trades SET {sets} WHERE id = :id", fields | {"id": trade_id})

    def trades_df(self) -> pd.DataFrame:
        df = pd.read_sql_query("SELECT * FROM trades ORDER BY open_time", self.conn)
        for col in ("open_time", "close_time"):
            df[col] = pd.to_datetime(df[col], utc=True, format="ISO8601")
        return df

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
