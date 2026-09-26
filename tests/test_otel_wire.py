"""OTLP over HTTP end to end: a real exporter posts to a local collector
stand-in, and the protobuf it received is decoded and checked."""

from __future__ import annotations

import gzip
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

pytest.importorskip("opentelemetry.exporter.otlp.proto.http")

from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (  # noqa: E402
    ExportLogsServiceRequest,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (  # noqa: E402
    ExportTraceServiceRequest,
)

from logquill import Logger, OTelLogsTransport, OTLPTransport, RunPlugin  # noqa: E402


class Collector:
    def __init__(self) -> None:
        self.requests: dict[str, list[bytes]] = {"/v1/traces": [], "/v1/logs": []}
        self.received = threading.Event()


@pytest.fixture()
def collector() -> Iterator[tuple[str, Collector]]:
    state = Collector()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            body = self.rfile.read(int(self.headers["Content-Length"]))
            if self.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            state.requests.setdefault(self.path, []).append(body)
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()
            state.received.set()

        def log_message(self, format: str, *args: Any) -> None:
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(
        target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}", state
    finally:
        httpd.shutdown()
        httpd.server_close()


def _attribute(attributes: Any, key: str) -> Any:
    for item in attributes:
        if item.key == key:
            return item.value
    raise KeyError(key)


def test_an_agent_run_reaches_a_collector_with_the_right_tree_and_usage_values(
    collector: tuple[str, Collector],
) -> None:
    base, state = collector
    logger = Logger(
        "app.agent",
        transports=[OTLPTransport(endpoint=f"{base}/v1/traces", service_name="agent-service")],
        plugins=[RunPlugin()],
    )

    with logger.span("run", operation="invoke_agent", agent_name="planner"):
        logger.llm_call(
            "chat",
            model="example-model",
            tokens_in=1200,
            tokens_out=340,
            finish_reason="stop",
            provider="anthropic",
        )
    logger.close()

    (body,) = state.requests["/v1/traces"]
    request = ExportTraceServiceRequest.FromString(body)
    (resource_spans,) = request.resource_spans
    assert (
        _attribute(resource_spans.resource.attributes, "service.name").string_value
        == "agent-service"
    )
    spans = {span.name: span for scope in resource_spans.scope_spans for span in scope.spans}
    assert set(spans) == {"invoke_agent planner", "chat example-model"}

    run, chat = spans["invoke_agent planner"], spans["chat example-model"]
    assert run.parent_span_id == b""
    assert chat.parent_span_id == run.span_id
    assert chat.trace_id == run.trace_id
    assert _attribute(chat.attributes, "gen_ai.usage.input_tokens").int_value == 1200
    assert _attribute(chat.attributes, "gen_ai.usage.output_tokens").int_value == 340
    assert _attribute(chat.attributes, "gen_ai.request.model").string_value == "example-model"
    assert _attribute(chat.attributes, "gen_ai.operation.name").string_value == "chat"
    assert (
        list(_attribute(chat.attributes, "gen_ai.response.finish_reasons").array_value.values)[
            0
        ].string_value
        == "stop"
    )


def test_logs_reach_a_collector_and_join_their_span_by_id(
    collector: tuple[str, Collector],
) -> None:
    base, state = collector
    logger = Logger(
        "app.agent",
        transports=[
            OTLPTransport(endpoint=f"{base}/v1/traces"),
            OTelLogsTransport(endpoint=f"{base}/v1/logs"),
        ],
        plugins=[RunPlugin()],
    )

    with logger.span("work", span_id="00f067aa0ba902b7"):
        logger.warn("something odd", user_id=42)
    logger.close()

    span = next(
        span
        for body in state.requests["/v1/traces"]
        for scope in ExportTraceServiceRequest.FromString(body).resource_spans[0].scope_spans
        for span in scope.spans
    )
    log_records = [
        record
        for body in state.requests["/v1/logs"]
        for scope in ExportLogsServiceRequest.FromString(body).resource_logs[0].scope_logs
        for record in scope.log_records
    ]
    warning = next(r for r in log_records if r.body.string_value == "something odd")
    assert warning.severity_text == "WARN"
    assert _attribute(warning.attributes, "user_id").int_value == 42
    # the span's own log line carries the span's id, so the two can be joined
    span_log = next(r for r in log_records if r.body.string_value == "work")
    assert span_log.span_id == span.span_id
    assert span_log.trace_id == span.trace_id
