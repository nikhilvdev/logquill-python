from __future__ import annotations

import asyncio
import sys

import pytest

from logquill import Logger
from logquill.transports.transport import CollectingTransport
from tests.test_instrument.fakes import IncompleteDetails, Response, install_fake_openai


@pytest.fixture(autouse=True)
def _fresh_module() -> None:
    sys.modules.pop("logquill.instrument.openai", None)
    import logquill.instrument.openai  # noqa: F401

    yield
    from logquill.instrument.openai import openai

    if openai.active:
        openai.uninstrument()


def test_chat_completions_are_instrumented(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_openai(monkeypatch)
    from openai.resources.chat.completions import Completions

    from logquill.instrument.openai import openai

    sink = CollectingTransport()
    openai(Logger("app", transports=[sink]))

    Completions().create(model="gpt-fake", messages=[])

    assert sink.records[0]["llm"] == {
        "model": "gpt-fake",
        "tokens_in": 8,
        "tokens_out": 3,
        "finish_reason": "stop",
        "latency_ms": sink.records[0]["llm"]["latency_ms"],
    }
    assert sink.records[0]["meta"]["provider"] == "openai"


def test_async_chat_completions_are_instrumented(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_openai(monkeypatch)
    from openai.resources.chat.completions import AsyncCompletions

    from logquill.instrument.openai import openai

    sink = CollectingTransport()
    openai(Logger("app", transports=[sink]))

    asyncio.run(AsyncCompletions().create(model="gpt-fake", messages=[]))

    assert sink.records[0]["llm"]["tokens_in"] == 8


def test_the_responses_api_is_instrumented_too(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_openai(monkeypatch)
    from openai.resources.responses import Responses

    from logquill.instrument.openai import openai

    sink = CollectingTransport()
    openai(Logger("app", transports=[sink]))

    Responses().create(model="gpt-fake", input="hi")

    assert sink.records[0]["llm"] == {
        "model": "gpt-fake",
        "tokens_in": 6,
        "tokens_out": 2,
        "finish_reason": "completed",
        "latency_ms": sink.records[0]["llm"]["latency_ms"],
    }


def test_an_incomplete_response_reports_its_own_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_openai(monkeypatch)
    from openai.resources.responses import Responses

    from logquill.instrument.openai import openai

    def create(self: object, **kwargs: object) -> Response:
        return Response(
            status="incomplete", incomplete_details=IncompleteDetails(reason="max_output_tokens")
        )

    Responses.create = create  # type: ignore[method-assign]
    sink = CollectingTransport()
    openai(Logger("app", transports=[sink]))

    Responses().create(model="gpt-fake", input="hi")

    assert sink.records[0]["llm"]["finish_reason"] == "max_output_tokens"


def test_a_streaming_chat_call_passes_through_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_openai(monkeypatch)
    from openai.resources.chat.completions import Completions

    from logquill.instrument.openai import openai

    sink = CollectingTransport()
    openai(Logger("app", transports=[sink]))

    Completions().create(model="gpt-fake", messages=[], stream=True)

    assert sink.records == []


def test_uninstrument_restores_all_four_methods(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_openai(monkeypatch)
    from openai.resources.chat.completions import AsyncCompletions, Completions
    from openai.resources.responses import AsyncResponses, Responses

    from logquill.instrument.openai import openai

    originals = (
        Completions.create,
        AsyncCompletions.create,
        Responses.create,
        AsyncResponses.create,
    )
    openai(Logger("app"))
    openai.uninstrument()

    assert (
        Completions.create,
        AsyncCompletions.create,
        Responses.create,
        AsyncResponses.create,
    ) == originals


def test_a_missing_openai_package_gives_an_install_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "openai.resources.chat", None)
    from logquill.instrument.openai import openai

    with pytest.raises(ImportError, match=r"pip install logquill\[instrument-openai\]"):
        openai(Logger("app"))
