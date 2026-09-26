from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, TypedDict, cast

from logquill.levels import Level

#: The record shape this version writes. Shared with logquill-js: a record
#: carries it as `schema_version` so a reader can tell which shape it has.
SCHEMA_VERSION = "2.0"

#: What a record with no `schema_version` — anything written by logquill 1.x —
#: is taken to be.
LEGACY_SCHEMA_VERSION = "1.0"

_VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)$")
_SUPPORTED_MAJOR = int(SCHEMA_VERSION.split(".")[0])


class LLMBlock(TypedDict, total=False):
    """The LLM-call fields, first-class on a record rather than free-form
    `meta` so cost and latency dashboards can rely on their names. Every key is
    optional; a record that isn't an LLM call has no `llm` block at all."""

    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: float
    finish_reason: str


class _RequiredRecordFields(TypedDict):
    schema_version: str
    timestamp: str
    level: str
    logger: str
    message: str
    meta: dict[str, Any]


class LogRecord(_RequiredRecordFields, total=False):
    """The cross-language record shape shared with logquill-js.

    `llm` is present only on LLM-call records. See `schema/record.schema.json`
    for the machine-readable definition both packages test against.
    """

    llm: LLMBlock


def utc_timestamp() -> str:
    """ISO8601 UTC timestamp with millisecond precision, matching JS `Date.toISOString()`."""
    now = datetime.now(timezone.utc)
    return f"{now.strftime('%Y-%m-%dT%H:%M:%S')}.{now.microsecond // 1000:03d}Z"


def create_record(
    *,
    level: Level,
    logger: str,
    message: str,
    meta: dict[str, Any],
    llm: LLMBlock | None = None,
) -> LogRecord:
    """Build a `LogRecord` stamped with `SCHEMA_VERSION` and the current UTC
    timestamp, and the level's string name (not its numeric value, per the
    cross-language record shape). `llm` is included only when given."""
    record = LogRecord(
        schema_version=SCHEMA_VERSION,
        timestamp=utc_timestamp(),
        level=level.name,
        logger=logger,
        message=message,
        meta=meta,
    )
    if llm is not None:
        record["llm"] = llm
    return record


def parse_record(raw: Mapping[str, Any]) -> LogRecord:
    """Read a record another process wrote — a decoded JSON log line — into
    the current shape, accepting both 2.x records and logquill 1.x ones.

    A record with no `schema_version` (everything 1.x wrote) comes back
    labelled `"1.0"`, with everything else untouched: the 1.x fields mean the
    same thing in 2.x, so nothing needs converting. A missing `meta` becomes
    `{}`. Keys this version doesn't know are kept, so a record from a newer
    minor version passes through without losing data. Returns a new dict; the
    input isn't modified.

    Raises `ValueError` — saying what to fix — if a required field is missing
    or has the wrong type, the level isn't one of `TRACE DEBUG INFO WARN ERROR
    FATAL`, or the record's `schema_version` is a newer major version than this
    logquill understands.
    """
    if not isinstance(raw, Mapping):
        raise ValueError(f"a log record must be a JSON object, got {type(raw).__name__}")

    record: dict[str, Any] = dict(raw)
    version = record.setdefault("schema_version", LEGACY_SCHEMA_VERSION)
    match = _VERSION_PATTERN.match(version) if isinstance(version, str) else None
    if match is None:
        raise ValueError(
            f"schema_version must be a string like '2.0', got {version!r} — is this a "
            "LogQuill record?"
        )
    if int(match.group(1)) > _SUPPORTED_MAJOR:
        raise ValueError(
            f"this record has schema_version {version!r}, newer than the {SCHEMA_VERSION!r} "
            "this logquill understands — upgrade logquill to read it"
        )

    for field in ("timestamp", "level", "logger", "message"):
        if not isinstance(record.get(field), str):
            raise ValueError(f"record field {field!r} must be a string, got {record.get(field)!r}")
    if record["level"] not in Level.__members__:
        raise ValueError(
            f"record level {record['level']!r} isn't one of "
            f"{', '.join(level.name for level in Level)} (upper case)"
        )

    meta = record.setdefault("meta", {})
    if not isinstance(meta, dict):
        raise ValueError(f"record field 'meta' must be an object, got {type(meta).__name__}")
    llm = record.get("llm")
    if llm is not None and not isinstance(llm, dict):
        raise ValueError(f"record field 'llm' must be an object, got {type(llm).__name__}")

    return cast(LogRecord, record)
