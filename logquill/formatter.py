from __future__ import annotations

import json
from typing import Protocol

from logquill.records import LogRecord


class Formatter(Protocol):
    """`format(record) -> string`, per the transport contract shared with logquill-js."""

    def format(self, record: LogRecord) -> str:
        """Render `record` to the string a transport will write."""
        ...


class JSONFormatter:
    """Serializes a record to the canonical JSON line shape."""

    def format(self, record: LogRecord) -> str:
        """Serializes `record` to a single compact JSON line; non-JSON-native
        values fall back to `str()` rather than raising."""
        return json.dumps(record, separators=(",", ":"), default=str)
