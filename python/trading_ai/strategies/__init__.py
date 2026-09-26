from trading_ai.strategies.base import Strategy
from trading_ai.strategies.rsi2_reversion import RSI2Both, RSI2Reversion
from trading_ai.strategies.session_breakout import NYBreakout, SessionBreakout
from trading_ai.strategies.trend_breakout import TrendBreakout
from trading_ai.strategies.turn_of_month import TurnOfMonth

STRATEGIES: dict[str, type[Strategy]] = {s.name: s for s in (TrendBreakout, RSI2Reversion, RSI2Both, TurnOfMonth, SessionBreakout, NYBreakout)}


def get_strategy(name: str) -> type[Strategy]:
    try:
        return STRATEGIES[name]
    except KeyError:
        raise ValueError(f"Unknown strategy '{name}'. Available: {', '.join(STRATEGIES)}") from None
