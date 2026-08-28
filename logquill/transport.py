from __future__ import annotations

from abc import ABC, abstractmethod

from logquill.formatter import Formatter, JSONFormatter
from logquill.records import LogRecord


class Transport(ABC):
    """Sink for log records, per the cross-language transport contract:
    `format(record) -> str`, `write(formatted, record)`, `close()` on shutdown.
    """

    def __init__(self, formatter: Formatter | None = None) -> None:
        self.formatter: Formatter = formatter or JSONFormatter()

    def format(self, record: LogRecord) -> str:
        return self.formatter.format(record)

    @abstractmethod
    def write(self, formatted: str, record: LogRecord) -> None: ...

    def close(self) -> None:  # noqa: B027 — intentionally optional to override
        """Flush/release resources on shutdown. No-op unless a transport overrides it."""


class CollectingTransport(Transport):
    """In-memory transport for tests: collects every (formatted, record) pair written to it."""

    def __init__(self, formatter: Formatter | None = None) -> None:
        super().__init__(formatter)
        self.formatted: list[str] = []
        self.records: list[LogRecord] = []
        self.closed = False

    def write(self, formatted: str, record: LogRecord) -> None:
        self.formatted.append(formatted)
        self.records.append(record)

    def close(self) -> None:
        self.closed = True
