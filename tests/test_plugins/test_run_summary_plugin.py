from __future__ import annotations

from logquill import Logger, RunPlugin
from logquill.plugins.run_summary_plugin import RunSummaryPlugin
from logquill.transports.transport import CollectingTransport


def _logger(**kwargs: object) -> tuple[Logger, CollectingTransport, RunSummaryPlugin]:
    sink = CollectingTransport()
    summary = RunSummaryPlugin(transports=[sink], **kwargs)  # type: ignore[arg-type]
    logger = Logger(
        "app.agent",
        transports=[sink],
        plugins=[RunPlugin(run_id="run-1"), summary],
        content_policy="full",
    )
    return logger, sink, summary


def _run_summary(sink: CollectingTransport) -> dict:
    (summary,) = (r for r in sink.records if r["meta"].get("kind") == "run_summary")
    return summary


def test_no_summary_until_the_outermost_span_closes() -> None:
    logger, sink, _ = _logger()

    with logger.span("run"):
        logger.info("step")
        assert all(r["meta"].get("kind") != "run_summary" for r in sink.records)


def test_summary_emitted_when_the_outermost_span_closes() -> None:
    logger, sink, _ = _logger()

    with logger.span("run"):
        logger.info("step")

    summary = _run_summary(sink)
    assert summary["message"] == "run summary"
    assert summary["logger"] == "app.run_summary"
    assert summary["level"] == "INFO"


def test_tokens_and_cost_are_summed_across_every_llm_call() -> None:
    logger, sink, _ = _logger()

    with logger.span("run"):
        logger.llm_call("chat", model="m", tokens_in=100, tokens_out=20, cost_usd=0.01)
        logger.llm_call("chat", model="m", tokens_in=50, tokens_out=10, cost_usd=0.02)

    summary = _run_summary(sink)
    assert summary["meta"]["tokens_in"] == 150
    assert summary["meta"]["tokens_out"] == 30
    assert summary["meta"]["cost_usd"] == 0.03


def test_tool_calls_are_counted() -> None:
    logger, sink, _ = _logger()

    with logger.span("run"):
        logger.action("call", tool="search")
        logger.action("call", tool="search")  # retry of the same tool
        logger.action("think")  # not a tool call — no `tool=`
        logger.observation("done", tool="search")

    summary = _run_summary(sink)
    assert summary["meta"]["tool_calls"] == 2


def test_retry_counts_are_summed() -> None:
    logger, sink, _ = _logger()

    with logger.span("run"):
        logger.action("call", tool="search")  # retry_count=None
        logger.action("call", tool="search")  # auto-tracked: retry_count=1

    summary = _run_summary(sink)
    assert summary["meta"]["retries"] == 1


def test_errors_are_counted() -> None:
    logger, sink, _ = _logger()

    with logger.span("run"):
        logger.error("first")
        logger.fatal("second")
        logger.warn("not counted")
        logger.info("not counted either")

    summary = _run_summary(sink)
    assert summary["meta"]["errors"] == 2


def test_record_count_and_duration_are_reported() -> None:
    logger, sink, _ = _logger()

    with logger.span("run"):
        logger.info("one")
        logger.info("two")

    summary = _run_summary(sink)
    # one + two + the root span's own closing record = 3
    assert summary["meta"]["record_count"] == 3
    assert isinstance(summary["meta"]["duration_ms"], float)


def test_summary_is_nested_under_the_runs_root_span() -> None:
    logger, sink, _ = _logger()

    with logger.span("run"):
        pass

    summary = _run_summary(sink)
    root = next(r for r in sink.records if r["message"] == "run")
    assert summary["meta"]["parent_span_id"] == root["meta"]["span_id"]


def test_a_run_with_no_errors_still_gets_a_summary() -> None:
    logger, sink, _ = _logger()

    with logger.span("run"):
        logger.info("fine")

    summary = _run_summary(sink)
    assert summary["meta"]["errors"] == 0


def test_two_runs_are_summarized_independently() -> None:
    sink = CollectingTransport()
    summary_plugin = RunSummaryPlugin(transports=[sink])
    logger_a = Logger(
        "app.agent",
        transports=[sink],
        plugins=[RunPlugin(run_id="run-a"), summary_plugin],
    )
    logger_b = Logger(
        "app.agent",
        transports=[sink],
        plugins=[RunPlugin(run_id="run-b"), summary_plugin],
    )

    with logger_a.span("run"):
        logger_a.action("call", tool="search")
    with logger_b.span("run"):
        pass

    summaries = {
        r["meta"]["run_id"]: r for r in sink.records if r["meta"].get("kind") == "run_summary"
    }
    assert summaries["run-a"]["meta"]["tool_calls"] == 1
    assert summaries["run-b"]["meta"]["tool_calls"] == 0


def test_a_record_with_no_run_id_is_ignored() -> None:
    sink = CollectingTransport()
    summary_plugin = RunSummaryPlugin(transports=[sink])
    logger = Logger("app.agent", transports=[sink], plugins=[summary_plugin])

    logger.info("loose, no run_id")

    assert sink.records == [sink.records[0]]  # just the one record, no summary


def test_a_nested_span_closing_does_not_trigger_a_summary() -> None:
    logger, sink, _ = _logger()

    with logger.span("run"):
        with logger.span("step"):
            pass
        assert all(r["meta"].get("kind") != "run_summary" for r in sink.records)


def test_aggregation_state_is_bounded_by_max_runs() -> None:
    sink = CollectingTransport()
    summary_plugin = RunSummaryPlugin(transports=[sink], max_runs=2)
    logger = Logger("app.agent", transports=[sink], plugins=[summary_plugin])

    for i in range(10):
        logger.info("step", run_id=f"r{i}")

    assert len(summary_plugin._stats) <= 2
