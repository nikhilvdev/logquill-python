from __future__ import annotations

import contextlib
from typing import Any

from logquill.levels import Level, parse_level
from logquill.plugin import Plugin
from logquill.records import LogRecord, create_record
from logquill.transport import Transport


class Logger:
    def __init__(
        self,
        name: str,
        level: int | str | Level = Level.INFO,
        transports: list[Transport] | None = None,
        plugins: list[Plugin] | None = None,
    ) -> None:
        self.name = name
        self._level = parse_level(level)
        self.transports: list[Transport] = list(transports) if transports else []
        self.plugins: list[Plugin] = list(plugins) if plugins else []

    @property
    def level(self) -> Level:
        return self._level

    def set_level(self, level: int | str | Level) -> None:
        self._level = parse_level(level)

    def use(self, plugin: Plugin) -> Logger:
        """Register a plugin. Returns `self` so calls can be chained."""
        self.plugins.append(plugin)
        return self

    def close(self) -> None:
        """Close every attached transport. Call on shutdown to flush buffered writes."""
        for transport in self.transports:
            transport.close()

    def _notify_error(self, plugin: Plugin, exc: Exception, record: LogRecord) -> None:
        # a broken error handler must not crash logging either
        with contextlib.suppress(Exception):
            plugin.on_error(exc, record)

    def _log(self, level: Level, message: str, meta: dict[str, Any]) -> LogRecord | None:
        if level < self._level:
            return None
        record = create_record(level=level, logger=self.name, message=message, meta=meta)

        for plugin in self.plugins:
            try:
                result = plugin.before_log(record)
            except Exception as exc:
                self._notify_error(plugin, exc, record)
                continue
            if result is None:
                return None
            record = result

        for transport in self.transports:
            transport.write(transport.format(record), record)

        for plugin in self.plugins:
            try:
                plugin.after_log(record)
            except Exception as exc:
                self._notify_error(plugin, exc, record)

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
