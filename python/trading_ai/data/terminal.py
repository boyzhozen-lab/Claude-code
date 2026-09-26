"""Work with the MT5 terminal's own folders: install/compile our EAs, the
RiskGuard kill switch and heartbeat."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trading_ai.config import PROJECT_ROOT
from trading_ai.data.mt5_client import MT5Error

MQL5_SOURCE = PROJECT_ROOT / "mql5"
EA_SUBFOLDER = "TradingAI"


@dataclass(frozen=True)
class TerminalPaths:
    data: Path      # File > Open Data Folder
    install: Path   # where terminal64.exe / metaeditor64.exe live

    @property
    def experts(self) -> Path:
        return self.data / "MQL5" / "Experts" / EA_SUBFOLDER

    @property
    def files(self) -> Path:
        return self.data / "MQL5" / "Files" / "trading_ai"

    @property
    def kill_switch(self) -> Path:
        return self.files / "kill_switch"

    @property
    def heartbeat(self) -> Path:
        return self.files / "heartbeat.json"


def terminal_paths(mt5: Any) -> TerminalPaths:
    info = mt5.terminal_info()
    if info is None:
        raise MT5Error(f"terminal_info failed: {mt5.last_error()}")
    return TerminalPaths(data=Path(info.data_path), install=Path(info.path))


def install_experts(paths: TerminalPaths, source: Path = MQL5_SOURCE) -> list[Path]:
    """Copy our .mq5 files into the terminal's MQL5/Experts/TradingAI folder."""
    paths.experts.mkdir(parents=True, exist_ok=True)
    installed = []
    for src in sorted((source / "Experts").glob("*.mq5")):
        dst = paths.experts / src.name
        shutil.copy2(src, dst)
        installed.append(dst)
    return installed


def _read_log(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-16", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def compile_expert(paths: TerminalPaths, mq5: Path) -> tuple[bool, str]:
    """Compile with MetaEditor. Returns (success, compiler log)."""
    editor = paths.install / "metaeditor64.exe"
    if not editor.exists():
        return False, f"MetaEditor not found at {editor}. Open the .mq5 in MetaEditor (F4) and press F7."
    log = mq5.with_suffix(".log")
    log.unlink(missing_ok=True)
    subprocess.run([str(editor), f"/compile:{mq5}", f"/log:{log}"], timeout=180, check=False)
    if not log.exists():
        return False, "MetaEditor produced no log."
    text = _read_log(log)
    ok = mq5.with_suffix(".ex5").exists() and " 0 errors" in text.replace(",", " ")
    return ok, text


def read_heartbeat(paths: TerminalPaths) -> dict[str, Any] | None:
    if not paths.heartbeat.exists():
        return None
    return json.loads(paths.heartbeat.read_text(encoding="latin-1"))
