from __future__ import annotations

import subprocess
import sys
from typing import Any

import pytest

pytest.importorskip("opentelemetry.sdk")

from opentelemetry.sdk.trace import ReadableSpan  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)
from opentelemetry.trace import SpanKind, StatusCode  # noqa: E402

from logquill import Logger, OTLPTransport, RunPlugin, TraceContextPlugin  # noqa: E402
from logquill.plugins.trace_context_plugin import (  # noqa: E402
    reset_traceparent,
    set_traceparent,
)


def _setup(**kwargs: Any) -> tuple[Logger, OTLPTransport, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    transport = OTLPTransport(span_exporter=exporter, processor="simple", **kwargs)
    logger = Logger("app.agent", level="TRACE", transports=[transport], plugins=[RunPlugin()])
    return logger, transport, exporter


def _by_name(spans: list[ReadableSpan]) -> dict[str, ReadableSpan]:
    return {span.name: span for span in spans}


def _attrs(span: ReadableSpan) -> dict[str, Any]:
    return dict(span.attributes or {})


def _record_an_agent_run(logger: Logger) -> None:
    with logger.span("run", operation="invoke_agent", agent_name="planner"):
        logger.thought("plan the work")  # not a span: ignored by the span exporter
        with logger.span("plan_step"):
            logger.llm_call(
                "chat",
                model="example-model",
                tokens_in=1200,
                tokens_out=340,
                cost_usd=0.0123,
                latency_ms=250,
                finish_reason="stop",
                provider="anthropic",
            )
        logger.action("look it up", tool="search", tool_call_id="call_1", duration_ms=40)
    logger.close()


def test_a_recorded_agent_run_exports_the_correct_span_tree() -> None:
    logger, _, exporter = _setup()

    _record_an_agent_run(logger)

    spans = _by_name(list(exporter.get_finished_spans()))
    assert set(spans) == {
        "invoke_agent planner",
        "plan_step",
        "chat example-model",
        "execute_tool search",
    }
    run, step = spans["invoke_agent planner"], spans["plan_step"]
    chat, tool = spans["chat example-model"], spans["execute_tool search"]

    assert run.parent is None
    assert step.parent is not None and step.parent.span_id == run.context.span_id
    assert chat.parent is not None and chat.parent.span_id == step.context.span_id
    assert tool.parent is not None and tool.parent.span_id == run.context.span_id
    # one run, one trace
    assert len({s.context.trace_id for s in spans.values()}) == 1


def test_the_llm_span_carries_the_usage_and_model_attributes() -> None:
    logger, _, exporter = _setup()

    _record_an_agent_run(logger)

    chat = _by_name(list(exporter.get_finished_spans()))["chat example-model"]
    assert chat.kind == SpanKind.CLIENT
    assert _attrs(chat) == {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "anthropic",
        "gen_ai.request.model": "example-model",
        "gen_ai.usage.input_tokens": 1200,
        "gen_ai.usage.output_tokens": 340,
        "gen_ai.response.finish_reasons": ("stop",),
        "logquill.cost_usd": 0.0123,
        "logquill.run_id": chat.attributes["logquill.run_id"],  # type: ignore[index]
    }


def test_agent_and_tool_spans_use_the_conventional_names_and_attributes() -> None:
    logger, _, exporter = _setup()

    _record_an_agent_run(logger)

    spans = _by_name(list(exporter.get_finished_spans()))
    run, tool = spans["invoke_agent planner"], spans["execute_tool search"]
    assert run.kind == SpanKind.CLIENT
    assert _attrs(run)["gen_ai.operation.name"] == "invoke_agent"
    assert _attrs(run)["gen_ai.agent.name"] == "planner"
    assert tool.kind == SpanKind.INTERNAL
    assert _attrs(tool)["gen_ai.operation.name"] == "execute_tool"
    assert _attrs(tool)["gen_ai.tool.name"] == "search"
    assert _attrs(tool)["gen_ai.tool.call.id"] == "call_1"
    assert "gen_ai.operation.name" not in _attrs(spans["plan_step"])


def test_span_start_and_end_come_from_the_record() -> None:
    logger, _, exporter = _setup()

    _record_an_agent_run(logger)

    spans = _by_name(list(exporter.get_finished_spans()))
    chat, tool = spans["chat example-model"], spans["execute_tool search"]
    assert chat.end_time - chat.start_time == pytest.approx(250_000_000, abs=1_000)
    assert tool.end_time - tool.start_time == pytest.approx(40_000_000, abs=1_000)


def test_a_trace_id_from_trace_context_is_used_as_the_otel_trace_id() -> None:
    exporter = InMemorySpanExporter()
    logger = Logger(
        "app",
        transports=[OTLPTransport(span_exporter=exporter, processor="simple")],
        plugins=[TraceContextPlugin()],
    )

    token = set_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
    try:
        with logger.span("work"):
            pass
    finally:
        reset_traceparent(token)

    (span,) = exporter.get_finished_spans()
    assert format(span.context.trace_id, "032x") == "4bf92f3577b34da6a3ce929d0e0e4736"


def test_a_span_keeps_its_own_span_id_so_children_and_logs_can_point_at_it() -> None:
    logger, _, exporter = _setup()
    with logger.span("outer", span_id="00f067aa0ba902b7"):
        pass
    logger.close()

    (span,) = exporter.get_finished_spans()
    assert format(span.context.span_id, "016x") == "00f067aa0ba902b7"


def test_a_span_id_that_is_not_hex_is_mapped_consistently() -> None:
    logger, _, exporter = _setup()
    parent_id = "3f0a6f4e-5c1b-4d0b-9d7a-0a1b2c3d4e5f"  # e.g. a LangChain run id
    with logger.span("parent", span_id=parent_id), logger.span("child"):
        pass
    logger.close()

    spans = _by_name(list(exporter.get_finished_spans()))
    assert spans["child"].parent is not None
    assert spans["child"].parent.span_id == spans["parent"].context.span_id


def test_failures_become_error_spans_with_an_error_type() -> None:
    logger, _, exporter = _setup()

    with pytest.raises(ValueError), logger.span("risky"):
        raise ValueError("bad input")
    logger.action("look it up", tool="search", error="TimeoutError: too slow")
    logger.close()

    spans = _by_name(list(exporter.get_finished_spans()))
    risky, tool = spans["risky"], spans["execute_tool search"]
    assert risky.status.status_code == StatusCode.ERROR
    assert risky.status.description == "ValueError: bad input"
    assert _attrs(risky)["error.type"] == "ValueError"
    assert tool.status.status_code == StatusCode.ERROR
    assert _attrs(tool)["error.type"] == "TimeoutError"


def test_state_diff_and_retry_count_are_exported() -> None:
    logger, _, exporter = _setup()
    state = {"n": 1}

    with logger.span("act", capture_state=lambda: state):
        state["n"] = 2
        logger.action("go", tool="search", duration_ms=1)
        logger.action("go", tool="search", duration_ms=1)
    logger.close()

    spans = list(exporter.get_finished_spans())
    act = _by_name(spans)["act"]
    (event,) = act.events
    assert event.name == "logquill.state_diff"
    assert event.attributes["logquill.state"] == '{"before":{"n":1},"after":{"n":2}}'  # type: ignore[index]
    retries = sorted(
        _attrs(s).get("logquill.retry_count", 0) for s in spans if s.name == "execute_tool search"
    )
    assert retries == [0, 1]


def test_records_that_are_not_spans_are_ignored() -> None:
    logger, _, exporter = _setup()

    logger.info("just a log line")
    logger.thought("thinking")
    logger.observation("saw something")
    logger.error("oops")

    assert exporter.get_finished_spans() == ()


def test_prompt_and_completion_text_is_not_exported_unless_asked_for() -> None:
    messages = [{"role": "user", "parts": [{"type": "text", "content": "secret prompt"}]}]

    off_logger, _, off = _setup()
    off_logger.llm_call("chat", model="m", input_messages=messages)
    on_logger, _, on = _setup(capture_content=True)
    on_logger.llm_call("chat", model="m", input_messages=messages)

    (off_span,) = off.get_finished_spans()
    (on_span,) = on.get_finished_spans()
    assert "gen_ai.input.messages" not in _attrs(off_span)
    assert "secret prompt" in _attrs(on_span)["gen_ai.input.messages"]


def test_content_capture_can_be_switched_on_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "true")
    logger, _, exporter = _setup()

    logger.llm_call("chat", model="m", output_messages=[{"role": "assistant", "parts": []}])

    (span,) = exporter.get_finished_spans()
    assert "gen_ai.output.messages" in _attrs(span)


def test_the_legacy_naming_generation_is_selectable_and_never_mixed_with_the_new() -> None:
    logger, _, exporter = _setup(semconv_version="legacy")

    logger.llm_call("chat", model="m", tokens_in=1, tokens_out=2, provider="openai")

    (span,) = exporter.get_finished_spans()
    attributes = _attrs(span)
    assert attributes["gen_ai.system"] == "openai"
    assert attributes["gen_ai.usage.prompt_tokens"] == 1
    assert attributes["gen_ai.usage.completion_tokens"] == 2
    assert "gen_ai.provider.name" not in attributes
    assert "gen_ai.usage.input_tokens" not in attributes


def test_the_environment_opt_in_selects_the_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental")
    logger, _, exporter = _setup()

    logger.llm_call("chat", model="m", tokens_in=1)

    (span,) = exporter.get_finished_spans()
    assert _attrs(span)["gen_ai.usage.input_tokens"] == 1


def test_the_service_name_becomes_a_resource_attribute() -> None:
    logger, _, exporter = _setup(service_name="checkout-agent")

    with logger.span("work"):
        pass

    (span,) = exporter.get_finished_spans()
    assert span.resource.attributes["service.name"] == "checkout-agent"


def test_flush_and_close_work_with_the_batch_processor() -> None:
    exporter = InMemorySpanExporter()
    transport = OTLPTransport(span_exporter=exporter)  # batch, the default
    logger = Logger("app", transports=[transport])

    with logger.span("work"):
        pass
    logger.flush()

    assert len(exporter.get_finished_spans()) == 1
    logger.close()


def test_a_bad_processor_is_rejected_up_front() -> None:
    with pytest.raises(ValueError, match="processor must be"):
        OTLPTransport(span_exporter=InMemorySpanExporter(), processor="eventually")


def test_importing_logquill_does_not_import_opentelemetry() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, logquill; print(any(m.startswith('opentelemetry') for m in sys.modules))",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == "False"


def test_a_missing_sdk_gives_an_install_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace", None)

    with pytest.raises(ImportError, match=r"pip install logquill\[otel\]"):
        OTLPTransport(span_exporter=InMemorySpanExporter())
