from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from logquill import JSONFormatter, Logger
from logquill.transports.transport import CollectingTransport


def _logger() -> tuple[Logger, CollectingTransport]:
    sink = CollectingTransport()
    return Logger("app.agent", transports=[sink]), sink


def test_llm_call_writes_the_first_class_llm_block() -> None:
    logger, sink = _logger()

    record = logger.llm_call(
        "chat",
        model="example-model",
        tokens_in=1200,
        tokens_out=340,
        cost_usd=0.0123,
        latency_ms=2150.5,
        finish_reason="stop",
        provider="openai",
    )

    assert record is sink.records[0]
    assert record["message"] == "chat"
    assert record["llm"] == {
        "model": "example-model",
        "tokens_in": 1200,
        "tokens_out": 340,
        "cost_usd": 0.0123,
        "latency_ms": 2150.5,
        "finish_reason": "stop",
    }
    assert record["meta"] == {"kind": "action", "provider": "openai"}
    assert record["level"] == "INFO"


def test_llm_call_leaves_out_fields_you_did_not_give() -> None:
    logger, _ = _logger()

    record = logger.llm_call(model="m", tokens_in=0)

    assert record is not None
    assert record["llm"] == {"model": "m", "tokens_in": 0}
    assert record["message"] == "llm_call"


def test_llm_call_with_nothing_to_report_has_no_llm_key() -> None:
    logger, _ = _logger()

    record = logger.llm_call()

    assert record is not None
    assert "llm" not in record


@pytest.mark.parametrize(
    "bad",
    [
        {"tokens_in": -1},
        {"tokens_in": 1.5},
        {"tokens_in": "12"},
        {"tokens_out": True},
        {"cost_usd": "0.1"},
        {"latency_ms": -0.5},
        {"model": 7},
        {"finish_reason": ["stop"]},
    ],
)
def test_a_value_that_breaks_the_contract_is_dropped_with_a_warning(
    bad: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    logger, _ = _logger()
    good = {"tokens_out": 3, "finish_reason": "stop"}

    with caplog.at_level(logging.WARNING, logger="logquill"):
        record = logger.llm_call(**{**good, **bad})

    assert record is not None
    assert record.get("llm") == ({k: v for k, v in good.items() if k not in bad} or None)
    assert "llm_call: ignoring" in caplog.text


def test_llm_call_respects_the_level_and_disable() -> None:
    import logquill

    logger = Logger("app.agent", level="ERROR")
    assert logger.llm_call(model="m") is None

    loud = Logger("mylib", level="INFO")
    logquill.disable("mylib")
    assert loud.llm_call(model="m") is None


def test_opt_views_have_llm_call_too() -> None:
    logger, sink = _logger()

    record = logger.opt(depth=0).llm_call("chat", model="m", tokens_in=3)

    assert record is not None
    assert record["llm"] == {"model": "m", "tokens_in": 3}
    assert record["meta"]["caller"]["function"] == "test_opt_views_have_llm_call_too"
    assert sink.records == [record]


def test_the_record_validates_against_the_published_schema() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    from pathlib import Path

    schema = json.loads(
        (Path(__file__).parent.parent / "schema" / "record.schema.json").read_text()
    )
    logger, _ = _logger()
    record = logger.llm_call(
        "chat",
        model="m",
        tokens_in=1,
        tokens_out=2,
        cost_usd=0.1,
        latency_ms=3,
        finish_reason="stop",
        provider="p",
    )

    jsonschema.validate(json.loads(JSONFormatter().format(record)), schema)  # type: ignore[arg-type]
