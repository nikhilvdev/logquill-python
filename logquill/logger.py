from __future__ import annotations

from typing import Any

from logquill.levels import Level, parse_level
from logquill.records import LogRecord, create_record
from logquill.transport import Transport


class Logger:
    def __init__(
        self,
        name: str,
        level: int | str | Level = Level.INFO,
        transports: list[Transport] | None = None,
    ) -> None:
        self.name = name
        self._level = parse_level(level)
        self.transports: list[Transport] = list(transports) if transports else []

    @property
    def level(self) -> Level:
        return self._level

    def set_level(self, level: int | str | Level) -> None:
        self._level = parse_level(level)

    def close(self) -> None:
        """Close every attached transport. Call on shutdown to flush buffered writes."""
        for transport in self.transports:
            transport.close()

    def _log(self, level: Level, message: str, meta: dict[str, Any]) -> LogRecord | None:
        if level < self._level:
            return None
        record = create_record(level=level, logger=self.name, message=message, meta=meta)
        for transport in self.transports:
            transport.write(transport.format(record), record)
        return record

    def trace(self, message: str, **meta: Any) -> LogRecord | None:
        return self._log(Level.TRACE, message, meta)

    def debug(self, message: str, **meta: Any) -> LogRecord | None:
        return self._log(Level.DEBUG, message, meta)

    def info(self, message: str, **meta: Any) -> LogRecord | None:
        return self._log(Level.INFO, message, meta)

    def warn(self, message: str, **meta: Any) -> LogRecord | None:
        return self._log(Level.WARN, message, meta)

    def error(self, message: str, **meta: Any) -> LogRecord | None:
        return self._log(Level.ERROR, message, meta)

    def fatal(self, message: str, **meta: Any) -> LogRecord | None:
        return self._log(Level.FATAL, message, meta)
