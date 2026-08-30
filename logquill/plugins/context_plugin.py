from __future__ import annotations

from typing import Any

from logquill.plugins.plugin import Plugin
from logquill.records import LogRecord


class ContextPlugin(Plugin):
    """Injects fixed key/value pairs into every record's `meta`.

    A value already present in a record's own `meta` wins over the fixed context.
    """

    def __init__(self, **context: Any) -> None:
        self.context = context

    def before_log(self, record: LogRecord) -> LogRecord | None:
        record["meta"] = {**self.context, **record["meta"]}
        return record
