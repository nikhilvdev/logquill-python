from __future__ import annotations

import logquill
from logquill import Logger
from logquill.transports.transport import CollectingTransport


def _logger(name: str) -> tuple[Logger, CollectingTransport]:
    sink = CollectingTransport()
    return Logger(name, transports=[sink]), sink


def test_everything_is_enabled_by_default() -> None:
    logger, sink = _logger("mylib")

    logger.info("hello")

    assert len(sink.records) == 1
    assert logquill.is_enabled("mylib")


def test_disable_silences_a_logger_and_everything_nested_under_it() -> None:
    parent, parent_sink = _logger("mylib")
    child = parent.child("http")
    sibling, sibling_sink = _logger("mylib2")

    logquill.disable("mylib")

    assert parent.info("x") is None
    assert child.info("x") is None
    assert sibling.info("x") is not None
    assert parent_sink.records == []
    assert len(sibling_sink.records) == 1


def test_enable_turns_a_disabled_library_back_on() -> None:
    logger, sink = _logger("mylib")
    logquill.disable("mylib")
    logquill.enable("mylib")

    logger.info("visible again")

    assert len(sink.records) == 1


def test_the_most_specific_rule_wins() -> None:
    quiet, _ = _logger("mylib.internal")
    loud, _ = _logger("mylib.http")
    logquill.disable("mylib")
    logquill.enable("mylib.http")

    assert quiet.info("x") is None
    assert loud.info("x") is not None


def test_disable_with_no_name_silences_everything_and_enable_can_carve_out() -> None:
    logquill.disable()
    other, _ = _logger("other")
    mine, _ = _logger("app")
    logquill.enable("app")

    assert other.info("x") is None
    assert mine.info("x") is not None


def test_disabled_spans_and_stdlib_bridge_records_are_dropped_too() -> None:
    import logging

    logger, sink = _logger("mylib")
    logquill.disable("mylib")
    handler = logquill.LogQuillHandler(logger)
    stdlib = logging.getLogger("toggle-test")
    stdlib.addHandler(handler)
    stdlib.propagate = False
    try:
        with logger.span("work"):
            pass
        stdlib.warning("nope")
    finally:
        stdlib.removeHandler(handler)

    assert sink.records == []


def test_disable_rejects_a_non_string_name() -> None:
    import pytest

    with pytest.raises(TypeError, match="logger name"):
        logquill.disable(123)  # type: ignore[arg-type]
