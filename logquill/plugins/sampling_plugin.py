from __future__ import annotations

import random
from typing import Callable

from logquill.plugins.plugin import Plugin
from logquill.records import LogRecord


class SamplingPlugin(Plugin):
    """Keeps roughly `rate` of records (0.0-1.0), dropping the rest."""

    def __init__(self, rate: float, rng: Callable[[], float] | None = None) -> None:
        if not 0.0 <= rate <= 1.0:
            raise ValueError(f"rate must be between 0 and 1, got {rate!r}")
        self.rate = rate
        self._rng = rng or random.random

    def before_log(self, record: LogRecord) -> LogRecord | None:
        return record if self._rng() < self.rate else None
