from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypedDict

from logquill.levels import Level


class LogRecord(TypedDict):
    """The cross-language record shape shared with logquill-js."""

    timestamp: str
    level: str
    logger: str
    message: str
    meta: dict[str, Any]


def utc_timestamp() -> str:
    """ISO8601 UTC timestamp with millisecond precision, matching JS `Date.toISOString()`."""
    now = datetime.now(timezone.utc)
    return f"{now.strftime('%Y-%m-%dT%H:%M:%S')}.{now.microsecond // 1000:03d}Z"


def create_record(*, level: Level, logger: str, message: str, meta: dict[str, Any]) -> LogRecord:
    return LogRecord(
        timestamp=utc_timestamp(),
        level=level.name,
        logger=logger,
        message=message,
        meta=meta,
    )
