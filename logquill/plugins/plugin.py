from __future__ import annotations

from typing import Callable

from logquill.records import LogRecord

MiddlewareFunc = Callable[[LogRecord], "LogRecord | None"]


class Plugin:
    """Base class for the plugin pipeline: `before_log`, `after_log`, `on_error`.

    Override only the hooks you need — the rest default to no-ops. A plugin
    hook that raises cannot crash logging: the pipeline catches it, routes it
    to `on_error`, and moves on.
    """

    def before_log(self, record: LogRecord) -> LogRecord | None:
        """Return a (possibly modified) record, or `None` to drop it."""
        return record

    def after_log(self, record: LogRecord) -> None:
        """Called after the record has been dispatched to every transport."""

    def on_error(self, exc: Exception, record: LogRecord) -> None:
        """Called when one of this plugin's own hooks raises."""


class FunctionPlugin(Plugin):
    """Wraps a plain `before_log`-style function as a `Plugin`.

    `Logger.use()` builds one of these automatically when given a function
    instead of a `Plugin` subclass — a one-off transform shouldn't require
    subclassing ceremony. There's no `next()` chaining: the pipeline is
    already an ordered list of hooks the `Logger` calls in sequence, so this
    is sugar for a single-method `Plugin`, not a new execution model.
    """

    def __init__(self, func: MiddlewareFunc) -> None:
        """`func` is the plain `before_log`-style function this instance
        delegates to."""
        self._func = func

    def before_log(self, record: LogRecord) -> LogRecord | None:
        """Delegates to the wrapped function."""
        return self._func(record)
