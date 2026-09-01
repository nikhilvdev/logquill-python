from __future__ import annotations

import uuid

from logquill.plugins.plugin import Plugin
from logquill.records import LogRecord


class RunPlugin(Plugin):
    """Stamps `meta.run_id` — a stable id grouping every record from one
    agent run — plus an incrementing `meta.step` counter, one per record
    processed through this plugin instance.

    Distinct from `TraceContextPlugin`'s `trace_id`: `run_id` scopes one
    agent run, `trace_id` follows one request across services. A run can
    span multiple traces (e.g. an agent that calls several downstream
    services); the two ids are independent.

    One instance is one run: attach a fresh `RunPlugin()` per run (typically
    via `logger.child("agent").use(RunPlugin())`), never a process-wide
    singleton shared across runs — otherwise concurrent runs would share
    both the run id and the step counter.

    A record that already carries `meta["run_id"]` (e.g. propagated from an
    upstream call) keeps its existing value; `meta["step"]` is always set
    from this instance's own counter.
    """

    def __init__(self, run_id: str | None = None) -> None:
        self.run_id = run_id or uuid.uuid4().hex
        self._step = 0

    def before_log(self, record: LogRecord) -> LogRecord | None:
        meta = record["meta"]
        meta.setdefault("run_id", self.run_id)
        meta["step"] = self._step
        self._step += 1
        return record
