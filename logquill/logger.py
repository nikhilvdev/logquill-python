from __future__ import annotations

import contextlib
import logging
from typing import Any

from logquill.levels import Level, parse_level
from logquill.plugins.context_plugin import ContextPlugin
from logquill.plugins.plugin import FunctionPlugin, MiddlewareFunc, Plugin
from logquill.records import LogRecord, create_record
from logquill.span import SpanContext, current_span_id
from logquill.transports.transport import Transport

_logger = logging.getLogger("logquill")


class Logger:
    def __init__(
        self,
        name: str,
        level: int | str | Level = Level.INFO,
        transports: list[Transport] | None = None,
        plugins: list[Plugin | MiddlewareFunc] | None = None,
    ) -> None:
        self.name = name
        self._level = parse_level(level)
        self.transports: list[Transport] = list(transports) if transports else []
        self.plugins: list[Plugin] = []
        for plugin in plugins or []:
            self.use(plugin)

    @property
    def level(self) -> Level:
        return self._level

    def set_level(self, level: int | str | Level) -> None:
        self._level = parse_level(level)

    def use(self, plugin: Plugin | MiddlewareFunc) -> Logger:
        """Register a plugin, or a plain `before_log`-style function.

        A function is wrapped internally as an anonymous `Plugin`
        (`FunctionPlugin`) — the same middleware ergonomics as Express/Koa,
        without needing to read the `Plugin` base class first. Returns
        `self` so calls can be chained.
        """
        if not isinstance(plugin, Plugin):
            plugin = FunctionPlugin(plugin)
        self.plugins.append(plugin)
        return self

    def child(self, name: str, /, **fixed_meta: Any) -> Logger:
        """A namespaced logger under this one: `f"{self.name}.{name}"`.

        Shares this logger's transports (the same sink instances, so
        `close()` on either flushes both) but starts with its own empty
        plugin list — plugins are per-logger middleware, not inherited, so
        a child can `.use(RunPlugin())` without attaching it to the
        parent's pipeline too. Any `fixed_meta` given is injected into
        every record the child produces, via an internal `ContextPlugin`.
        """
        child_logger = Logger(f"{self.name}.{name}", level=self._level, transports=self.transports)
        if fixed_meta:
            child_logger.use(ContextPlugin(**fixed_meta))
        return child_logger

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

        parent_span_id = current_span_id()
        if parent_span_id is not None:
            record["meta"].setdefault("parent_span_id", parent_span_id)

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
            try:
                transport.write(transport.format(record), record)
            except Exception:
                # a transport that can't format or write this particular record
                # (e.g. a circular reference in `meta`) must not crash the caller
                _logger.exception("%s: failed to write a log record", type(transport).__name__)

        for plugin in self.plugins:
            try:
                plugin.after_log(record)
            except Exception as exc:
                self._notify_error(plugin, exc, record)

        return record

    # `message: str, /` (positional-only) on every method below: a caller
    # passing `**meta` where `meta` happens to contain a `"message"` key
    # (e.g. forwarding an adversarial or framework-supplied dict) would
    # otherwise collide with the `message` parameter and raise
    # `TypeError: got multiple values for argument 'message'`, crashing the
    # caller — exactly what the plugin pipeline's hypothesis tests assert
    # never happens (see `tests/test_plugin_pipeline_properties.py`).
    def trace(self, message: str, /, **meta: Any) -> LogRecord | None:
        return self._log(Level.TRACE, message, meta)

    def debug(self, message: str, /, **meta: Any) -> LogRecord | None:
        return self._log(Level.DEBUG, message, meta)

    def info(self, message: str, /, **meta: Any) -> LogRecord | None:
        return self._log(Level.INFO, message, meta)

    def warn(self, message: str, /, **meta: Any) -> LogRecord | None:
        return self._log(Level.WARN, message, meta)

    def error(self, message: str, /, **meta: Any) -> LogRecord | None:
        return self._log(Level.ERROR, message, meta)

    def fatal(self, message: str, /, **meta: Any) -> LogRecord | None:
        return self._log(Level.FATAL, message, meta)

    def thought(self, message: str, /, **meta: Any) -> LogRecord | None:
        """`.info()` tagged `meta.kind = "thought"` — an agent's internal
        reasoning step, for harness/agentic tracing."""
        return self._log(Level.INFO, message, {"kind": "thought", **meta})

    def action(self, message: str, /, **meta: Any) -> LogRecord | None:
        """`.info()` tagged `meta.kind = "action"` — an agent taking an
        action (a tool call, an LLM request), for harness/agentic tracing."""
        return self._log(Level.INFO, message, {"kind": "action", **meta})

    def observation(self, message: str, /, **meta: Any) -> LogRecord | None:
        """`.info()` tagged `meta.kind = "observation"` — the result an
        agent observed from an action, for harness/agentic tracing."""
        return self._log(Level.INFO, message, {"kind": "observation", **meta})

    def decision(self, message: str, /, **meta: Any) -> LogRecord | None:
        """`.info()` tagged `meta.kind = "decision"` — an agent's concluding
        decision for a step or run, for harness/agentic tracing."""
        return self._log(Level.INFO, message, {"kind": "decision", **meta})

    def span(
        self,
        name: str,
        /,
        *,
        span_id: str | None = None,
        parent_span_id: str | None = None,
        **meta: Any,
    ) -> SpanContext:
        """`with agent_log.span("call_llm"):` — on exit, emits one record
        carrying `meta.span_id` and `meta.duration_ms`; every record logged
        inside the block (through any method) is automatically stamped with
        `meta.parent_span_id` pointing at this span, so nested/sub-agent
        calls reconstruct their exact nesting when sorted by
        `span_id`/`parent_span_id`. Still emits its record — at `ERROR`,
        with `meta.error` set — if the block raises; the exception itself
        propagates unchanged.

        `span_id`/`parent_span_id` normally auto-generate/auto-nest; pass
        them explicitly to adopt an id handed in from elsewhere (see
        `logquill.adapters.langchain.LangChainAdapter` for an example).
        """
        return SpanContext(self, name, span_id=span_id, parent_span_id=parent_span_id, **meta)
