from __future__ import annotations

import contextlib
import logging
from typing import Any

from logquill.context import current_context
from logquill.exceptions import format_exc_info
from logquill.levels import Level, parse_level
from logquill.plugins.context_plugin import ContextPlugin
from logquill.plugins.plugin import FunctionPlugin, MiddlewareFunc, Plugin
from logquill.records import LogRecord, create_record
from logquill.span import SpanContext, current_span_id
from logquill.transports.transport import Transport
from logquill.worker import AsyncWorker, BackpressurePolicy

_logger = logging.getLogger("logquill")


class Logger:
    """A named, leveled logger that runs records through a plugin pipeline
    before writing them to one or more transports.

    Construct directly, or via `.child()` to derive a namespaced logger that
    shares this one's transports. See `__init__` for what `async_dispatch`
    changes about ordering.
    """

    def __init__(
        self,
        name: str,
        level: int | str | Level = Level.INFO,
        transports: list[Transport] | None = None,
        plugins: list[Plugin | MiddlewareFunc] | None = None,
        async_dispatch: bool = False,
        max_queue_size: int = 10_000,
        backpressure: BackpressurePolicy = "drop_oldest",
    ) -> None:
        """`async_dispatch=True` moves per-record transport writes (and the
        `after_log` plugin hooks that follow them) onto a background thread,
        via an internal `AsyncWorker` — so `.info()`/`.error()`/... return
        without waiting on a transport's I/O. `before_log` plugin hooks
        still run synchronously on the caller's thread, since they can
        filter/transform the record and a later hook or transport needs to
        see the result in order.

        `max_queue_size`/`backpressure` are only meaningful with
        `async_dispatch=True` — see `AsyncWorker` for what each
        `backpressure` policy does under a sustained burst.
        """
        self.name = name
        self._level = parse_level(level)
        self.transports: list[Transport] = list(transports) if transports else []
        self.plugins: list[Plugin] = []
        for plugin in plugins or []:
            self.use(plugin)
        self._worker: AsyncWorker | None = (
            AsyncWorker(max_queue_size=max_queue_size, backpressure=backpressure)
            if async_dispatch
            else None
        )

    @property
    def level(self) -> Level:
        """The minimum level this logger currently accepts."""
        return self._level

    def set_level(self, level: int | str | Level) -> None:
        """Change the minimum level this logger accepts; accepts an int, a
        level name, or a `Level` member."""
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
        # Share the parent's worker (if any) rather than spinning up a second
        # background thread: both loggers write to the same transport
        # instances, so their dispatch belongs on the same queue/thread.
        child_logger._worker = self._worker
        return child_logger

    def flush(self, timeout: float | None = None) -> bool:
        """Wait for every record already submitted for async dispatch to
        finish writing, then flush each transport's own internal buffer
        (e.g. `BatchingTransport`) — without closing anything.

        Unlike `close()`, safe to call repeatedly mid-lifetime: this is
        what `with_lambda`/`with_cloud_function`/`with_azure_function` call
        before a serverless invocation returns, since a warm container
        reuses this same `Logger`/its transports on the next invocation.

        Returns whether the async queue (if any) fully drained within
        `timeout`; always `True` when `async_dispatch` wasn't enabled, since
        dispatch already happened synchronously before this call.
        """
        drained = self._worker.drain(timeout) if self._worker is not None else True
        for transport in self.transports:
            transport.flush()
        return drained

    async def flush_async(self, timeout: float | None = None) -> bool:
        """`asyncio`-friendly `flush()` — awaits the drain instead of
        blocking the calling thread. See `flush()`.
        """
        drained = await self._worker.drain_async(timeout) if self._worker is not None else True
        for transport in self.transports:
            transport.flush()
        return drained

    def close(self, timeout: float | None = 5.0) -> None:
        """Stop async dispatch (draining any queued records first, up to
        `timeout` seconds) and close every attached transport. Call on
        process shutdown — after this, the transports may release
        resources a later log call would need, so don't call it on a
        `Logger` you intend to keep using (see `flush()` for that case).
        """
        if self._worker is not None:
            self._worker.close(timeout)
        for transport in self.transports:
            transport.close()

    def _notify_error(self, plugin: Plugin, exc: Exception, record: LogRecord) -> None:
        # a broken error handler must not crash logging either
        with contextlib.suppress(Exception):
            plugin.on_error(exc, record)

    def _dispatch(self, record: LogRecord) -> None:
        """Write `record` to every transport and run `after_log` hooks.
        This is the half of `_log` that does I/O — with `async_dispatch=True`
        it runs on the worker thread instead of the caller's, which is the
        entire non-blocking-dispatch contract in one method boundary.
        """
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

    def _log(self, level: Level, message: str, meta: dict[str, Any]) -> LogRecord | None:
        if level < self._level:
            return None

        if "exc_info" in meta:
            stack = format_exc_info(meta.pop("exc_info"))
            if stack is not None:
                meta["stack"] = stack

        record = create_record(level=level, logger=self.name, message=message, meta=meta)

        bound_context = current_context()
        if bound_context:
            record["meta"] = {**bound_context, **record["meta"]}

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

        if self._worker is not None:
            self._worker.submit(lambda: self._dispatch(record))
        else:
            self._dispatch(record)

        return record

    # `message: str, /` (positional-only) on every method below: a caller
    # passing `**meta` where `meta` happens to contain a `"message"` key
    # (e.g. forwarding an adversarial or framework-supplied dict) would
    # otherwise collide with the `message` parameter and raise
    # `TypeError: got multiple values for argument 'message'`, crashing the
    # caller — exactly what the plugin pipeline's hypothesis tests assert
    # never happens (see `tests/test_plugin_pipeline_properties.py`).
    def trace(self, message: str, /, **meta: Any) -> LogRecord | None:
        """Log at `TRACE`. Returns the emitted record, or `None` if filtered
        by level or dropped by a plugin."""
        return self._log(Level.TRACE, message, meta)

    def debug(self, message: str, /, **meta: Any) -> LogRecord | None:
        """Log at `DEBUG`. Returns the emitted record, or `None` if filtered
        by level or dropped by a plugin."""
        return self._log(Level.DEBUG, message, meta)

    def info(self, message: str, /, **meta: Any) -> LogRecord | None:
        """Log at `INFO`. Returns the emitted record, or `None` if filtered
        by level or dropped by a plugin."""
        return self._log(Level.INFO, message, meta)

    def warn(self, message: str, /, **meta: Any) -> LogRecord | None:
        """Log at `WARN`. Returns the emitted record, or `None` if filtered
        by level or dropped by a plugin."""
        return self._log(Level.WARN, message, meta)

    def error(self, message: str, /, **meta: Any) -> LogRecord | None:
        """`exc_info=` (an exception instance, `True` for the exception
        currently being handled, or an explicit `(type, value, traceback)`
        tuple — the same shapes stdlib `logging` accepts) formats a
        traceback into `meta["stack"]` and is otherwise not kept in `meta`
        as-is, since a raw exception object isn't serializable. Every
        `Logger` method accepts it, not just this one."""
        return self._log(Level.ERROR, message, meta)

    def fatal(self, message: str, /, **meta: Any) -> LogRecord | None:
        """Log at `FATAL`. Returns the emitted record, or `None` if filtered
        by level or dropped by a plugin."""
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
