from __future__ import annotations

from logquill.records import LogRecord


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
