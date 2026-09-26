"""Load project settings from config/settings.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from trading_ai.backtest.challenge import ChallengeRules

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
    history_years_d1: int
    data_dir: Path
    journal_db: Path
    costs: dict[str, float] = field(default_factory=dict)  # round-trip, price units
    challenge: dict[str, ChallengeRules] = field(default_factory=dict)
    ai_provider: str = "anthropic"
    ai_model: str = "claude-opus-5"
    ai_effort: str = "medium"

    @property
    def bars_dir(self) -> Path:
        return self.data_dir / "bars"

    @property
    def env_path(self) -> Path:
        return self.project_root / ".env"

    @property
    def specs_path(self) -> Path:
        return self.data_dir / "symbols.json"

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
        history_years_d1=int(download.get("years_d1", download.get("years", 5))),
        data_dir=resolve(paths.get("data_dir", "data")),
        journal_db=resolve(paths.get("journal_db", "data/journal.db")),
        costs={k: float(v) for k, v in raw.get("costs", {}).items()},
        challenge=_challenge_rules(raw.get("challenge", {})),
        ai_provider=raw.get("ai", {}).get("provider", "anthropic"),
        ai_model=raw.get("ai", {}).get("model", "claude-opus-5"),
        ai_effort=raw.get("ai", {}).get("effort", "medium"),
    )


FTMO_DEFAULTS = {
    "phase1": ChallengeRules(10.0, 5.0, 10.0, 4),
    "phase2": ChallengeRules(5.0, 5.0, 10.0, 4),
}


def _challenge_rules(raw: dict) -> dict[str, ChallengeRules]:
    rules = dict(FTMO_DEFAULTS)
    for phase, values in raw.items():
        try:
            rules[phase] = ChallengeRules(
                profit_target=float(values["profit_target"]),
                max_daily_loss=float(values["max_daily_loss"]),
                max_total_loss=float(values["max_total_loss"]),
                min_trading_days=int(values.get("min_trading_days", 0)),
                max_days=int(values.get("max_days", 0)),
            )
        except KeyError as e:
            raise ConfigError(f"[challenge.{phase}] is missing {e}") from None
    return rules
