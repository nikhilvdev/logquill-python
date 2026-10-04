"""The exit criterion for the flight recorder: a sustained burst of
low-level records across many runs, almost none of which error, stays
memory-bounded — the buffer's own bookkeeping never exceeds its configured
limits, and peak memory during the burst doesn't grow with the burst size.
Slow-ish and memory-instrumented, so it lives here rather than in the
default `pytest` run — see `measure.py`'s module docstring for why these
are a separate CI job.
"""

from __future__ import annotations

import tracemalloc

from logquill import Logger
from logquill.plugins.flight_recorder_plugin import FlightRecorderPlugin
from logquill.transports.transport import CollectingTransport

BURST = 100_000
MAX_BUFFERED_RECORDS = 2_000
MAX_RUNS = 200

#: However large the burst, buffering low-level records for thousands of
#: concurrent runs must stay nowhere near proportional to the burst size.
MEMORY_BUDGET_BYTES = 15_000_000


def test_a_sustained_burst_of_mostly_passing_runs_stays_memory_bounded() -> None:
    sink = CollectingTransport()
    recorder = FlightRecorderPlugin(
        transports=[sink], max_buffered_records=MAX_BUFFERED_RECORDS, max_runs=MAX_RUNS
    )
    logger = Logger("app.agent", level="DEBUG", transports=[sink], plugins=[recorder])

    tracemalloc.start()
    try:
        baseline, _ = tracemalloc.get_traced_memory()
        for i in range(BURST):
            run_id = f"run-{i % 10_000}"
            logger.debug("step", run_id=run_id, i=i, payload="x" * 80)
            if i % 50_000 == 0:  # a rare run actually errors
                logger.error("oops", run_id=run_id)
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert recorder._buffered_count <= MAX_BUFFERED_RECORDS
    assert len(recorder._buffer) <= MAX_RUNS

    peak_bytes = peak - baseline
    assert peak_bytes < MEMORY_BUDGET_BYTES, (
        f"buffering a {BURST:,}-record burst used {peak_bytes:,} bytes against a "
        f"budget of {MEMORY_BUDGET_BYTES:,} — memory grew with the burst, not the bound"
    )


def test_a_single_run_that_never_errors_is_dropped_once_evicted_not_leaked() -> None:
    """A burst entirely under one run_id that never reaches flush_at: once
    the record cap is hit, the *oldest* buffered records for that run are
    evicted — this run's own buffer never grows past the configured cap
    even though it alone accounts for the whole burst."""
    sink = CollectingTransport()
    recorder = FlightRecorderPlugin(transports=[sink], max_buffered_records=500, max_runs=10)
    logger = Logger("app.agent", level="DEBUG", transports=[sink], plugins=[recorder])

    for i in range(20_000):
        logger.debug("step", run_id="single-run", i=i)

    assert recorder._buffered_count <= 500
    assert sink.records == []  # never errored: nothing shipped
