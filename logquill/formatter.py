from __future__ import annotations

import json
from typing import Protocol

from logquill.records import LogRecord


class Formatter(Protocol):
    """`format(record) -> string`, per the transport contract shared with logquill-js."""

    def format(self, record: LogRecord) -> str: ...


class JSONFormatter:
    """Serializes a record to the canonical JSON line shape."""

    def format(self, record: LogRecord) -> str:
        return json.dumps(record, separators=(",", ":"), default=str)
