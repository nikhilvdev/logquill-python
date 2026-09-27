from __future__ import annotations

import asyncio
import sys

import pytest

from logquill import Logger
from logquill.transports.transport import CollectingTransport
from tests.test_instrument.fakes import install_fake_anthropic


def _reload() -> None:
    sys.modules.pop("logquill.instrument.anthropic", None)
    import logquill.instrument.anthropic  # noqa: F401


@pytest.fixture(autouse=True)
def _fresh_module(monkeypatch: pytest.MonkeyPatch) -> None:
    _reload()
    yield
    from logquill.instrument.anthropic import anthropic

    if anthropic.active:
        anthropic.uninstrument()


def test_a_sync_call_emits_llm_call_with_no_code_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_anthropic(monkeypatch)
    from anthropic.resources.messages.messages import Messages

    from logquill.instrument.anthropic import anthropic

    sink = CollectingTransport()
    logger = Logger("app", transports=[sink])
    anthropic(logger)

    response = Messages().create(model="claude-fake", max_tokens=100, messages=[])

    assert response.model == "claude-fake"  # the real return value still reaches the caller
    assert len(sink.records) == 1
    record = sink.records[0]
    assert record["llm"] == {
        "model": "claude-fake",
        "tokens_in": 10,
        "tokens_out": 4,
        "finish_reason": "end_turn",
        "latency_ms": record["llm"]["latency_ms"],
    }
    assert record["meta"]["provider"] == "anthropic"
    assert isinstance(record["llm"]["latency_ms"], float)


def test_an_async_call_is_instrumented_too(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_anthropic(monkeypatch)
    from anthropic.resources.messages.messages import AsyncMessages

    from logquill.instrument.anthropic import anthropic

    sink = CollectingTransport()
    logger = Logger("app", transports=[sink])
    anthropic(logger)

    asyncio.run(AsyncMessages().create(model="claude-fake", max_tokens=100, messages=[]))

    assert len(sink.records) == 1
    assert sink.records[0]["llm"]["tokens_in"] == 10


def test_a_streaming_call_passes_through_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    install_fake_anthropic(monkeypatch, calls=calls)
    from anthropic.resources.messages.messages import Messages

    from logquill.instrument.anthropic import anthropic

    sink = CollectingTransport()
    anthropic(Logger("app", transports=[sink]))

    Messages().create(model="claude-fake", max_tokens=100, messages=[], stream=True)

    assert calls == ["sync"]  # the real (fake) create() still ran
    assert sink.records == []  # but nothing was logged — streaming is a known gap


def test_uninstrument_restores_the_original_method(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_anthropic(monkeypatch)
    from anthropic.resources.messages.messages import Messages

    from logquill.instrument.anthropic import anthropic

    original = Messages.create
    anthropic(Logger("app"))
    assert Messages.create is not original

    anthropic.uninstrument()

    assert Messages.create is original
    anthropic.uninstrument()  # idempotent


def test_instrumenting_twice_without_uninstrument_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_anthropic(monkeypatch)
    from logquill.instrument.anthropic import anthropic

    anthropic(Logger("app"))

    with pytest.raises(RuntimeError, match="already active"):
        anthropic(Logger("app"))


def test_a_broken_logger_does_not_break_the_real_call(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_anthropic(monkeypatch)
    from anthropic.resources.messages.messages import Messages

    from logquill.instrument.anthropic import anthropic

    class ExplodingLogger(Logger):
        def llm_call(self, *args: object, **kwargs: object) -> None:  # type: ignore[override]
            raise RuntimeError("logging is broken")

    anthropic(ExplodingLogger("app"))

    response = Messages().create(model="claude-fake", max_tokens=100, messages=[])

    assert response.model == "claude-fake"  # the API call's result still comes back


def test_a_missing_anthropic_package_gives_an_install_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "anthropic.resources.messages", None)
    from logquill.instrument.anthropic import anthropic

    with pytest.raises(ImportError, match=r"pip install logquill\[instrument-anthropic\]"):
        anthropic(Logger("app"))


def test_importing_logquill_instrument_does_not_import_anthropic() -> None:
    import subprocess

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, logquill.instrument; "
            "print(any(m.startswith('anthropic') for m in sys.modules))",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == "False"
