from __future__ import annotations

from collections.abc import Iterable

from logquill.plugin import Plugin
from logquill.records import LogRecord

DEFAULT_REDACTED_KEYS = frozenset({"password", "token", "secret", "api_key", "authorization"})


class RedactPlugin(Plugin):
    """Replaces sensitive `meta` values, matched by key (case-insensitive), with a placeholder."""

    def __init__(
        self,
        keys: Iterable[str] = DEFAULT_REDACTED_KEYS,
        replacement: str = "***",
    ) -> None:
        self.keys = {key.lower() for key in keys}
        self.replacement = replacement

    def before_log(self, record: LogRecord) -> LogRecord | None:
        meta = record["meta"]
        record["meta"] = {
            key: self.replacement if key.lower() in self.keys else value
            for key, value in meta.items()
        }
        return record
