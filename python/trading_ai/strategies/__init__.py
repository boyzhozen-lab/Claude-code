from trading_ai.strategies.base import Strategy
from trading_ai.strategies.rsi2_reversion import RSI2Reversion
from trading_ai.strategies.trend_breakout import TrendBreakout

STRATEGIES: dict[str, type[Strategy]] = {s.name: s for s in (TrendBreakout, RSI2Reversion)}


def get_strategy(name: str) -> type[Strategy]:
    try:
        return STRATEGIES[name]
    except KeyError:
        raise ValueError(f"Unknown strategy '{name}'. Available: {', '.join(STRATEGIES)}") from None
