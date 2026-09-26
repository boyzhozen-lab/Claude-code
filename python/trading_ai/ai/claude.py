"""Claude-written commentary for trading reports.

The numbers in every report are computed in Python; Claude only explains them
in plain Lao and points out what needs attention. It never places trades.
"""

from __future__ import annotations

import json
from typing import Any

import anthropic

# Server-side refusal fallback: routes a declined request to a suitable model
# inside the same call. Only sent for models documented to support it.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = {"claude-opus-5", "claude-fable-5-1"}

SYSTEM_PROMPT = """You write short monitoring reports for a retail trader in Laos who runs an \
automated trading system (MT5 expert advisors on an Exness demo account, preparing for a prop-firm \
challenge). Write in Lao. The reader is not a programmer.

Rules:
- Use only the facts in the JSON you are given. Never invent numbers, trades or events.
- Do not predict prices or suggest discretionary trades. The system trades by fixed, tested rules; \
the trader's job is to keep it running and not interfere.
- Point out anything that needs action: RiskGuard not OK, MT5/EA problems, trades the EA missed or \
extra trades the backtest did not expect (forward-check), unusual slippage, drawdown near limits.
- A handful of trades says little about whether a strategy works; say so when relevant instead of \
drawing conclusions from small samples.
- Plain text for Telegram: short lines, a few emoji at most, no tables, no Markdown headings.
- Daily report: at most 10 lines. Weekly report: at most 25 lines. End with 1-3 concrete action \
items for the trader, or say that no action is needed."""


class AIError(RuntimeError):
    pass


def write_commentary(facts: dict[str, Any], period: str, model: str, effort: str = "medium") -> str:
    client = anthropic.Anthropic(max_retries=3, timeout=180.0)
    request: dict[str, Any] = {
        "model": model,
        "max_tokens": 16000,
        "system": SYSTEM_PROMPT,
        "output_config": {"effort": effort},
        "messages": [{
            "role": "user",
            "content": f"Write the {period} report from these facts:\n\n"
                       + json.dumps(facts, ensure_ascii=False, indent=1, default=str),
        }],
    }
    if model in FALLBACK_MODELS:
        request |= {"betas": [FALLBACK_BETA], "fallbacks": "default"}
    try:
        response = client.beta.messages.create(**request)
    except anthropic.AuthenticationError:
        raise AIError("Claude API key is missing or invalid: check ANTHROPIC_API_KEY in .env") from None
    except anthropic.PermissionDeniedError as e:
        raise AIError(f"Claude API permission denied (billing or model access?): {e.message}") from None
    except anthropic.NotFoundError:
        raise AIError(f"Model '{model}' not found: check [ai] model in config/settings.toml") from None
    except anthropic.RateLimitError:
        raise AIError("Claude API rate limit reached; try again later") from None
    except anthropic.APIStatusError as e:
        raise AIError(f"Claude API error {e.status_code}: {e.message} (request {e.request_id})") from None
    except anthropic.APIConnectionError:
        raise AIError("Cannot reach the Claude API (network)") from None

    if response.stop_reason == "refusal":
        raise AIError("Claude declined to write this report")
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if not text:
        raise AIError(f"Claude returned no text (stop reason: {response.stop_reason})")
    return text


def check_connection(model: str) -> str:
    """Tiny request to confirm the key, billing and model work."""
    return write_commentary({"test": True, "note": "Connection test. Reply with one short Lao sentence."},
                            "test", model, effort="low")
