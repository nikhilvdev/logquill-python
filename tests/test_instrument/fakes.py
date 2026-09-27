"""Fake stand-ins for the provider SDKs `logquill.instrument.*` patches — the
same `sys.modules` injection pattern the framework adapter tests use (see
`tests/test_adapters/test_langchain_adapter.py`), so these tests exercise the
real patching code against objects shaped like the real SDKs' without
requiring the actual (heavier) packages to be installed.
"""

from __future__ import annotations

import types
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass
class Message:
    """Stands in for `anthropic.types.Message`."""

    model: str = "claude-fake"
    stop_reason: str | None = "end_turn"
    usage: Usage = field(default_factory=lambda: Usage(input_tokens=10, output_tokens=4))


def install_fake_anthropic(monkeypatch: Any, *, calls: list[str] | None = None) -> None:
    def create(self: Any, **kwargs: Any) -> Message:
        if calls is not None:
            calls.append("sync")
        return Message()

    async def async_create(self: Any, **kwargs: Any) -> Message:
        if calls is not None:
            calls.append("async")
        return Message()

    messages_module = types.ModuleType("anthropic.resources.messages.messages")
    messages_module.Messages = type("Messages", (), {"create": create})  # type: ignore[attr-defined]
    messages_module.AsyncMessages = type(  # type: ignore[attr-defined]
        "AsyncMessages", (), {"create": async_create}
    )
    package = types.ModuleType("anthropic.resources.messages")
    package.messages = messages_module  # type: ignore[attr-defined]
    anthropic_module = types.ModuleType("anthropic")
    resources_module = types.ModuleType("anthropic.resources")
    resources_module.messages = package  # type: ignore[attr-defined]
    anthropic_module.resources = resources_module  # type: ignore[attr-defined]

    import sys

    monkeypatch.setitem(sys.modules, "anthropic", anthropic_module)
    monkeypatch.setitem(sys.modules, "anthropic.resources", resources_module)
    monkeypatch.setitem(sys.modules, "anthropic.resources.messages", package)
    monkeypatch.setitem(sys.modules, "anthropic.resources.messages.messages", messages_module)


@dataclass
class Choice:
    finish_reason: str | None = "stop"


@dataclass
class ChatCompletion:
    """Stands in for `openai.types.chat.ChatCompletion`."""

    model: str = "gpt-fake"
    usage: Usage = field(default_factory=lambda: Usage(prompt_tokens=8, completion_tokens=3))
    choices: list[Choice] = field(default_factory=lambda: [Choice()])


@dataclass
class IncompleteDetails:
    reason: str | None = None


@dataclass
class Response:
    """Stands in for `openai.types.responses.Response`."""

    model: str = "gpt-fake"
    status: str = "completed"
    incomplete_details: IncompleteDetails | None = None
    usage: Usage = field(default_factory=lambda: Usage(input_tokens=6, output_tokens=2))


def install_fake_openai(monkeypatch: Any, *, calls: list[str] | None = None) -> None:
    def chat_create(self: Any, **kwargs: Any) -> ChatCompletion:
        if calls is not None:
            calls.append("chat.sync")
        return ChatCompletion()

    async def async_chat_create(self: Any, **kwargs: Any) -> ChatCompletion:
        if calls is not None:
            calls.append("chat.async")
        return ChatCompletion()

    def responses_create(self: Any, **kwargs: Any) -> Response:
        if calls is not None:
            calls.append("responses.sync")
        return Response()

    async def async_responses_create(self: Any, **kwargs: Any) -> Response:
        if calls is not None:
            calls.append("responses.async")
        return Response()

    completions_module = types.ModuleType("openai.resources.chat.completions")
    completions_module.Completions = type(  # type: ignore[attr-defined]
        "Completions", (), {"create": chat_create}
    )
    completions_module.AsyncCompletions = type(  # type: ignore[attr-defined]
        "AsyncCompletions", (), {"create": async_chat_create}
    )
    responses_module = types.ModuleType("openai.resources.responses")
    responses_module.Responses = type(  # type: ignore[attr-defined]
        "Responses", (), {"create": responses_create}
    )
    responses_module.AsyncResponses = type(  # type: ignore[attr-defined]
        "AsyncResponses", (), {"create": async_responses_create}
    )
    chat_module = types.ModuleType("openai.resources.chat")
    chat_module.completions = completions_module  # type: ignore[attr-defined]
    resources_module = types.ModuleType("openai.resources")
    resources_module.chat = chat_module  # type: ignore[attr-defined]
    resources_module.responses = responses_module  # type: ignore[attr-defined]
    openai_module = types.ModuleType("openai")
    openai_module.resources = resources_module  # type: ignore[attr-defined]

    import sys

    monkeypatch.setitem(sys.modules, "openai", openai_module)
    monkeypatch.setitem(sys.modules, "openai.resources", resources_module)
    monkeypatch.setitem(sys.modules, "openai.resources.chat", chat_module)
    monkeypatch.setitem(sys.modules, "openai.resources.chat.completions", completions_module)
    monkeypatch.setitem(sys.modules, "openai.resources.responses", responses_module)


@dataclass
class LitellmResponse:
    """Stands in for `litellm.types.utils.ModelResponse`."""

    model: str = "litellm-fake"
    usage: Usage = field(default_factory=lambda: Usage(prompt_tokens=5, completion_tokens=1))
    choices: list[Choice] = field(default_factory=lambda: [Choice(finish_reason="stop")])
    _hidden_params: dict[str, Any] = field(
        default_factory=lambda: {"custom_llm_provider": "openai"}
    )


def install_fake_litellm(
    monkeypatch: Any,
    *,
    calls: list[str] | None = None,
    completion: Callable[..., Any] | None = None,
    acompletion: Callable[..., Any] | None = None,
) -> None:
    def default_completion(**kwargs: Any) -> LitellmResponse:
        if calls is not None:
            calls.append("sync")
        return LitellmResponse()

    async def default_acompletion(**kwargs: Any) -> LitellmResponse:
        if calls is not None:
            calls.append("async")
        return LitellmResponse()

    litellm_module = types.ModuleType("litellm")
    litellm_module.completion = completion or default_completion  # type: ignore[attr-defined]
    litellm_module.acompletion = acompletion or default_acompletion  # type: ignore[attr-defined]

    import sys

    monkeypatch.setitem(sys.modules, "litellm", litellm_module)
