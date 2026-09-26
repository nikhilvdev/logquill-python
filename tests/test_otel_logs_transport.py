from __future__ import annotations

import sys
from typing import Any

import pytest

pytest.importorskip("opentelemetry.sdk")

from opentelemetry._logs import SeverityNumber  # noqa: E402
from opentelemetry.sdk._logs import export as _log_export  # noqa: E402

# renamed in newer SDKs; the old name warns
InMemoryLogExporter = (
    getattr(_log_export, "InMemoryLogRecordExporter", None) or _log_export.InMemoryLogExporter
)

from logquill import Logger, OTelLogsTransport, RunPlugin  # noqa: E402


def _setup(**kwargs: Any) -> tuple[Logger, InMemoryLogExporter]:
    exporter = InMemoryLogExporter()
    transport = OTelLogsTransport(log_exporter=exporter, processor="simple", **kwargs)
    return Logger("app.api", level="TRACE", transports=[transport], plugins=[RunPlugin()]), exporter


def _emitted(exporter: InMemoryLogExporter) -> list[Any]:
    return [item.log_record for item in exporter.get_finished_logs()]


def test_every_record_becomes_a_log_record_with_body_and_severity() -> None:
    logger, exporter = _setup()

    logger.trace("t")
    logger.debug("d")
    logger.info("i")
    logger.warn("w")
    logger.error("e")
    logger.fatal("f")

    emitted = _emitted(exporter)
    assert [r.body for r in emitted] == ["t", "d", "i", "w", "e", "f"]
    assert [r.severity_text for r in emitted] == [
        "TRACE",
        "DEBUG",
        "INFO",
        "WARN",
        "ERROR",
        "FATAL",
    ]
    assert [r.severity_number for r in emitted] == [
        SeverityNumber.TRACE,
        SeverityNumber.DEBUG,
        SeverityNumber.INFO,
        SeverityNumber.WARN,
        SeverityNumber.ERROR,
        SeverityNumber.FATAL,
    ]


def test_meta_becomes_attributes_with_structure_flattened_to_json() -> None:
    logger, exporter = _setup()

    logger.info(
        "hello", user_id=42, ok=True, ratio=0.5, tags=["a", "b"], nested={"a": [1]}, none=None
    )

    attributes = dict(_emitted(exporter)[0].attributes)
    assert attributes["user_id"] == 42
    assert attributes["ok"] is True
    assert attributes["ratio"] == 0.5
    assert attributes["tags"] == ("a", "b")
    assert attributes["nested"] == '{"a":[1]}'
    assert "none" not in attributes
    assert attributes["logquill.logger"] == "app.api"
    assert attributes["logquill.schema_version"] == "2.0"


def test_a_mixed_list_becomes_a_json_string() -> None:
    logger, exporter = _setup()

    logger.info("hello", mixed=[1, "a"])

    assert dict(_emitted(exporter)[0].attributes)["mixed"] == '[1,"a"]'


def test_a_traceback_goes_to_the_standard_exception_attribute() -> None:
    logger, exporter = _setup()

    try:
        _ = 1 / 0
    except ZeroDivisionError as exc:
        logger.error("failed", exc_info=exc)

    attributes = dict(_emitted(exporter)[0].attributes)
    assert "ZeroDivisionError" in attributes["exception.stacktrace"]
    assert "stack" not in attributes


def test_the_ids_match_the_ones_the_span_exporter_uses() -> None:
    logger, exporter = _setup()

    with logger.span("work", span_id="00f067aa0ba902b7"):
        pass

    record = _emitted(exporter)[0]
    assert format(record.span_id, "016x") == "00f067aa0ba902b7"
    assert record.trace_id is not None and record.trace_id != 0


def test_an_llm_block_adds_the_standard_usage_attributes() -> None:
    logger, exporter = _setup()

    logger.llm_call(
        "chat", model="m", tokens_in=7, tokens_out=3, cost_usd=0.25, finish_reason="stop"
    )

    attributes = dict(_emitted(exporter)[0].attributes)
    assert attributes["gen_ai.usage.input_tokens"] == 7
    assert attributes["gen_ai.usage.output_tokens"] == 3
    assert attributes["gen_ai.request.model"] == "m"
    assert attributes["logquill.cost_usd"] == 0.25


def test_flush_and_close_with_the_batch_processor() -> None:
    exporter = InMemoryLogExporter()
    logger = Logger("app", transports=[OTelLogsTransport(log_exporter=exporter)])

    logger.info("hello")
    logger.flush()

    assert len(exporter.get_finished_logs()) == 1
    logger.close()


def test_a_bad_processor_is_rejected_up_front() -> None:
    with pytest.raises(ValueError, match="processor must be"):
        OTelLogsTransport(log_exporter=InMemoryLogExporter(), processor="later")


def test_a_missing_sdk_gives_an_install_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk._logs", None)

    with pytest.raises(ImportError, match=r"pip install logquill\[otel\]"):
        OTelLogsTransport(log_exporter=InMemoryLogExporter())
