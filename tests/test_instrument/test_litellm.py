from __future__ import annotations

import asyncio
import sys

import pytest

from logquill import Logger
from logquill.transports.transport import CollectingTransport
from tests.test_instrument.fakes import install_fake_litellm


@pytest.fixture(autouse=True)
def _fresh_module() -> None:
    sys.modules.pop("logquill.instrument.litellm", None)
    import logquill.instrument.litellm  # noqa: F401

    yield
    from logquill.instrument.litellm import litellm

    if litellm.active:
        litellm.uninstrument()


def test_a_sync_completion_is_instrumented(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_litellm(monkeypatch)
    import litellm as litellm_module

    from logquill.instrument.litellm import litellm

    sink = CollectingTransport()
    litellm(Logger("app", transports=[sink]))

    litellm_module.completion(model="litellm-fake", messages=[])

    assert sink.records[0]["llm"] == {
        "model": "litellm-fake",
        "tokens_in": 5,
        "tokens_out": 1,
        "finish_reason": "stop",
        "latency_ms": sink.records[0]["llm"]["latency_ms"],
    }
    # litellm resolves the real underlying provider; we surface it as-is
    assert sink.records[0]["meta"]["provider"] == "openai"


def test_an_async_completion_is_instrumented(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_litellm(monkeypatch)
    import litellm as litellm_module

    from logquill.instrument.litellm import litellm

    sink = CollectingTransport()
    litellm(Logger("app", transports=[sink]))

    asyncio.run(litellm_module.acompletion(model="litellm-fake", messages=[]))

    assert sink.records[0]["llm"]["tokens_in"] == 5


def test_a_streaming_completion_passes_through_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    install_fake_litellm(monkeypatch, calls=calls)
    import litellm as litellm_module

    from logquill.instrument.litellm import litellm

    sink = CollectingTransport()
    litellm(Logger("app", transports=[sink]))

    litellm_module.completion(model="litellm-fake", messages=[], stream=True)

    assert calls == ["sync"]
    assert sink.records == []


def test_uninstrument_restores_both_functions(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_litellm(monkeypatch)
    import litellm as litellm_module

    from logquill.instrument.litellm import litellm

    original_completion = litellm_module.completion
    original_acompletion = litellm_module.acompletion
    litellm(Logger("app"))
    litellm.uninstrument()

    assert litellm_module.completion is original_completion
    assert litellm_module.acompletion is original_acompletion


def test_a_missing_litellm_package_gives_an_install_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "litellm", None)
    from logquill.instrument.litellm import litellm

    with pytest.raises(ImportError, match=r"pip install logquill\[instrument-litellm\]"):
        litellm(Logger("app"))
