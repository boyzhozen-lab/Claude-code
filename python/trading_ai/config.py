"""Load project settings from config/settings.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "settings.toml"


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    project_root: Path
    broker_name: str
    server_timezone: str
    terminal_path: str | None
    symbols: dict[str, str]  # internal name -> broker symbol
    timeframes: list[str]
    history_years: int
    data_dir: Path
    journal_db: Path

    @property
    def bars_dir(self) -> Path:
        return self.data_dir / "bars"

    def broker_symbol(self, internal: str) -> str:
        try:
            return self.symbols[internal]
        except KeyError:
            known = ", ".join(self.symbols)
            raise ConfigError(f"Unknown symbol '{internal}'. Known: {known}") from None

    def internal_symbol(self, broker_symbol: str) -> str:
        """Map a broker symbol back to its internal name (unmapped names pass through)."""
        for internal, broker in self.symbols.items():
            if broker == broker_symbol:
                return internal
        return broker_symbol


def load_settings(path: Path | str | None = None) -> Settings:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.is_file():
        raise ConfigError(f"Config file not found: {config_path}")
    with config_path.open("rb") as f:
        raw = tomllib.load(f)

    # config/settings.toml sits one level below the project root.
    root = config_path.resolve().parent.parent

    def resolve(p: str) -> Path:
        candidate = Path(p)
        return candidate if candidate.is_absolute() else root / candidate

    broker = raw.get("broker", {})
    download = raw.get("download", {})
    paths = raw.get("paths", {})
    symbols = raw.get("symbols", {})
    if not symbols:
        raise ConfigError("[symbols] section is empty")

    return Settings(
        project_root=root,
        broker_name=broker.get("name", "unknown"),
        server_timezone=broker.get("server_timezone", "UTC"),
        terminal_path=broker.get("terminal_path") or None,
        symbols=dict(symbols),
        timeframes=list(download.get("timeframes", ["M15", "H1", "D1"])),
        history_years=int(download.get("years", 5)),
        data_dir=resolve(paths.get("data_dir", "data")),
        journal_db=resolve(paths.get("journal_db", "data/journal.db")),
    )
