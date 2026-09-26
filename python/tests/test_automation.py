import json
import time
from types import SimpleNamespace

import pytest

from conftest import Position, deal
from trading_ai.cli import main
from trading_ai.env import load_env, read_env, set_env_value
from trading_ai.notify import telegram


@pytest.fixture
def sent(monkeypatch):
    """Capture Telegram messages instead of sending them."""
    box = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    monkeypatch.setattr(telegram, "_call", lambda token, method, params: box.append(params["text"]) or {})
    return box


def test_env_read_set_and_load(tmp_path, monkeypatch):
    for key in ("TELEGRAM_CHAT_ID", "TELEGRAM_BOT_TOKEN"):   # restored after the test
        monkeypatch.setenv(key, "")
    env = tmp_path / ".env"
    env.write_text("# comment\nANTHROPIC_API_KEY=sk-ant-x\nTELEGRAM_BOT_TOKEN=\n")
    set_env_value(env, "TELEGRAM_CHAT_ID", "123")
    set_env_value(env, "TELEGRAM_BOT_TOKEN", "abc")
    assert read_env(env) == {"ANTHROPIC_API_KEY": "sk-ant-x", "TELEGRAM_BOT_TOKEN": "abc", "TELEGRAM_CHAT_ID": "123"}
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    load_env(env)
    import os
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-x"


def test_telegram_split_and_chat_id(monkeypatch):
    chunks = telegram.split_message("a" * 9000, limit=4000)
    assert [len(c) for c in chunks] == [4000, 4000, 1000]
    lines = telegram.split_message("x\n" * 3000, limit=4000)
    assert all(len(c) <= 4000 for c in lines) and "".join(lines) == "x\n" * 3000
    updates = [{"message": {"chat": {"id": 1}}}, {"message": {"chat": {"id": 777}}}]
    monkeypatch.setattr(telegram, "_call", lambda *a: updates)
    assert telegram.find_chat_id("t") == "777"


def test_claude_commentary_request_and_refusal(monkeypatch):
    from trading_ai.ai import claude
    calls = []

    class FakeClient:
        def __init__(self, **kw):
            self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

        def create(self, **kw):
            calls.append(kw)
            stop = "refusal" if kw["model"] == "refuse" else "end_turn"
            return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="thinking"),
                                                              SimpleNamespace(type="text", text=" ສະບາຍດີ ")])

    monkeypatch.setattr(claude.anthropic, "Anthropic", FakeClient)
    assert claude.write_commentary({"x": 1}, "daily", "claude-opus-5") == "ສະບາຍດີ"
    assert calls[0]["fallbacks"] == "default" and calls[0]["betas"] == [claude.FALLBACK_BETA]
    assert calls[0]["output_config"] == {"effort": "medium"}
    claude.write_commentary({"x": 1}, "daily", "claude-sonnet-5")
    assert "fallbacks" not in calls[1]
    with pytest.raises(claude.AIError):
        claude.write_commentary({}, "daily", "refuse")


def _terminal(fake_mt5, tmp_path, state="STATE_OK"):
    fake_mt5.data_path = str(tmp_path / "term")
    files = tmp_path / "term" / "MQL5" / "Files" / "trading_ai"
    files.mkdir(parents=True, exist_ok=True)
    (files / "heartbeat.json").write_text(json.dumps({"state": state, "daily_pnl": -12.5}))
    return files


def test_watchdog_first_run_then_new_and_closed_trades(fake_mt5, config_file, tmp_path, sent):
    _terminal(fake_mt5, tmp_path)
    cfg = ["--config", str(config_file)]
    assert main(cfg + ["watchdog"]) == 0
    assert any("Watchdog" in m for m in sent)

    sent.clear()
    fake_mt5.positions = [Position(9, "XAUUSDm", 0, 0.1, 2000.0, 1990.0, 0.0, 3.5, 2201, 0)]
    now = int(time.time())
    fake_mt5.deals = [deal(1, 8, now - 7200, 0, 0, 0.1, 2000.0, magic=2201),
                      deal(2, 8, now - 3600, 1, 1, 0.1, 2010.0, profit=100.0, reason=5, magic=2201)]
    assert main(cfg + ["watchdog"]) == 0
    assert any("ເປີດອໍເດີ GOLD long" in m for m in sent)
    assert any("ປິດອໍເດີ GOLD" in m and "+100.00" in m for m in sent)

    sent.clear()
    assert main(cfg + ["watchdog"]) == 0
    assert sent == []        # nothing new, no repeats


def test_watchdog_alerts_once_on_problem_and_on_recovery(fake_mt5, config_file, tmp_path, sent):
    files = _terminal(fake_mt5, tmp_path, state="STATE_DAILY_LOCK")
    cfg = ["--config", str(config_file)]
    assert main(cfg + ["watchdog"]) == 1
    assert any("STATE_DAILY_LOCK" in m for m in sent)
    sent.clear()
    assert main(cfg + ["watchdog"]) == 1
    assert sent == []        # same problem is not repeated within 6 hours
    (files / "heartbeat.json").write_text(json.dumps({"state": "STATE_OK"}))
    assert main(cfg + ["watchdog"]) == 0
    assert any("ປົກກະຕິ" in m for m in sent)


def test_report_without_ai(fake_mt5, config_file, tmp_path, sent):
    _terminal(fake_mt5, tmp_path)
    fake_mt5.positions = [Position(9, "XAUUSDm", 1, 0.2, 2000.0, 2010.0, 0.0, -4.0, 2201, 0)]
    cfg = ["--config", str(config_file)]
    assert main(cfg + ["fetch-bars", "--timeframes", "D1", "--years", "1"]) == 0
    assert main(cfg + ["report", "--period", "weekly", "--no-ai"]) == 0
    [text] = sent
    assert "ລາຍງານປະຈຳອາທິດ" in text and "GOLD short 0.2 lot" in text and "ປົກກະຕິ" in text
    assert list((config_file.parent.parent / "reports").glob("report_weekly_*.txt"))


def test_telegram_setup_saves_chat_id(config_file, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    monkeypatch.setattr(telegram, "_call", lambda token, method, params:
                        [{"message": {"chat": {"id": 555}}}] if method == "getUpdates" else {})
    assert main(["--config", str(config_file), "telegram-setup"]) == 0
    assert read_env(config_file.parent.parent / ".env")["TELEGRAM_CHAT_ID"] == "555"
