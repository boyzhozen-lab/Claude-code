"""Strategy interface used by the backtest engine.

A strategy looks at bars that have closed and marks signals on them. The
engine acts on a signal at the OPEN of the next bar, so a strategy can never
trade on information it would not have had.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

import pandas as pd

SIGNAL_COLUMNS = ["long_entry", "short_entry", "long_exit", "short_exit", "stop_dist", "target_dist"]


class Strategy(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    default_params: ClassVar[dict[str, Any]]
    # Small grid for walk-forward selection; keep it small to limit overfitting.
    param_grid: ClassVar[dict[str, list[Any]]]
    max_bars: ClassVar[int | None] = None  # time exit, in bars
    default_timeframe: ClassVar[str] = "D1"
    default_symbols: ClassVar[tuple[str, ...]] = ()  # empty = every symbol in config

    def __init__(self, **params: Any):
        unknown = set(params) - set(self.default_params)
        if unknown:
            raise ValueError(f"{self.name}: unknown params {sorted(unknown)}")
        self.params = self.default_params | params

    @abstractmethod
    def signals(self, bars: pd.DataFrame) -> pd.DataFrame:
        """Return a frame aligned with `bars` holding SIGNAL_COLUMNS.

        stop_dist/target_dist are price distances from the entry; target_dist
        may be NaN for no fixed target.
        """

    def label(self) -> str:
        return f"{self.name}({', '.join(f'{k}={v}' for k, v in self.params.items())})"
