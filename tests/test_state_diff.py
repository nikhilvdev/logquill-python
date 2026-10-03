from __future__ import annotations

from typing import Any

from logquill import Logger
from logquill.transports.transport import CollectingTransport


def _logger() -> tuple[Logger, CollectingTransport]:
    sink = CollectingTransport()
    # content_policy="full": these tests are about capture_state's diffing
    # logic, not the privacy policy that governs meta.state_diff's visibility
    # by default (see tests/test_privacy.py for that).
    return Logger("app.agent", transports=[sink], content_policy="full"), sink


def _span_meta(sink: CollectingTransport) -> dict[str, Any]:
    return sink.records[-1]["meta"]


def test_state_diff_records_only_the_keys_that_changed() -> None:
    logger, sink = _logger()
    state = {"items": 1, "user": "ada", "step": "plan"}

    with logger.span("act", capture_state=lambda: state):
        state["items"] = 2
        state["step"] = "act"

    assert _span_meta(sink)["state_diff"] == {
        "before": {"items": 1, "step": "plan"},
        "after": {"items": 2, "step": "act"},
    }


def test_added_and_removed_keys_show_on_one_side_only() -> None:
    logger, sink = _logger()
    state: dict[str, Any] = {"gone": 1, "kept": 1}

    with logger.span("act", capture_state=lambda: state):
        del state["gone"]
        state["new"] = 2

    assert _span_meta(sink)["state_diff"] == {"before": {"gone": 1}, "after": {"new": 2}}


def test_an_in_place_mutation_of_nested_state_is_seen() -> None:
    logger, sink = _logger()
    state = {"messages": ["a"]}

    with logger.span("act", capture_state=lambda: state):
        state["messages"].append("b")

    assert _span_meta(sink)["state_diff"] == {
        "before": {"messages": ["a"]},
        "after": {"messages": ["a", "b"]},
    }


def test_no_change_means_no_state_diff() -> None:
    logger, sink = _logger()
    state = {"n": 1}

    with logger.span("act", capture_state=lambda: state):
        pass

    assert "state_diff" not in _span_meta(sink)


def test_non_dict_state_records_the_whole_values() -> None:
    logger, sink = _logger()
    counter = [0]

    with logger.span("act", capture_state=lambda: counter[0]):
        counter[0] = 5

    assert _span_meta(sink)["state_diff"] == {"before": 0, "after": 5}


def test_a_capture_function_that_raises_never_breaks_the_traced_code() -> None:
    logger, sink = _logger()

    def broken() -> Any:
        raise RuntimeError("cannot snapshot")

    with logger.span("act", capture_state=broken):
        pass

    assert "state_diff" not in _span_meta(sink)
    assert _span_meta(sink)["kind"] == "span"


def test_state_that_cannot_be_copied_is_skipped() -> None:
    logger, sink = _logger()

    class Uncopyable:
        def __deepcopy__(self, memo: Any) -> Any:
            raise TypeError("no copies")

    with logger.span("act", capture_state=lambda: {"handle": Uncopyable()}):
        pass

    assert "state_diff" not in _span_meta(sink)


def test_the_diff_is_recorded_even_if_the_block_raises() -> None:
    logger, sink = _logger()
    state = {"n": 1}

    try:
        with logger.span("act", capture_state=lambda: state):
            state["n"] = 2
            raise ValueError("boom")
    except ValueError:
        pass

    meta = _span_meta(sink)
    assert meta["state_diff"] == {"before": {"n": 1}, "after": {"n": 2}}
    assert meta["error"] == "ValueError: boom"


def test_an_explicit_state_diff_in_meta_wins() -> None:
    logger, sink = _logger()
    state = {"n": 1}

    with logger.span("act", capture_state=lambda: state, state_diff={"mine": True}):
        state["n"] = 2

    assert _span_meta(sink)["state_diff"] == {"mine": True}
