from __future__ import annotations

import time
from typing import Any
from uuid import UUID

try:
    from langchain_core.callbacks import BaseCallbackHandler  # type: ignore[import-not-found]
except ImportError as exc:
    raise ImportError(
        "logquill.adapters.langchain requires the optional `langchain-core` "
        "dependency — install with `pip install logquill[langchain]`."
    ) from exc

from logquill.adapters.base import LogQuillAdapter
from logquill.logger import Logger
from logquill.span import SpanContext


def _span_ids(run_id: UUID, parent_run_id: UUID | None) -> dict[str, Any]:
    ids: dict[str, Any] = {"span_id": str(run_id)}
    if parent_run_id is not None:
        ids["parent_span_id"] = str(parent_run_id)
    return ids


def _tool_name(serialized: dict[str, Any] | None, fallback: str) -> str:
    if isinstance(serialized, dict):
        name = serialized.get("name")
        if isinstance(name, str) and name:
            return name
    return fallback


# `type: ignore[misc]` — BaseCallbackHandler types as `Any` whenever
# langchain-core isn't installed in the environment running mypy (it's an
# optional dependency, never in this project's `dev` extra — see
# pyproject.toml), and mypy refuses to let a class subclass something typed
# `Any`. With the real package installed, this subclasses the genuine
# `BaseCallbackHandler` and the ignore is inert.
class LangChainAdapter(LogQuillAdapter, BaseCallbackHandler):  # type: ignore[misc]
    """Maps LangChain's `BaseCallbackHandler` events onto LogQuill calls —
    LangGraph is covered for free, since it shares LangChain's callback
    system.

    Pass an instance into a chain/agent invocation's `callbacks=[...]`, the
    same way any other LangChain tracing handler (LangSmith, Langfuse, ...)
    is wired in — no other instrumentation needed:

        from logquill.adapters.langchain import LangChainAdapter
        from logquill.plugins.run_plugin import RunPlugin

        handler = LangChainAdapter(log.child("agent").use(RunPlugin()))
        llm = ChatOpenAI(callbacks=[handler])

    Event mapping:

    | LangChain callback                              | LogQuill call                     |
    |--------------------------------------------------|-----------------------------------|
    | `on_chain_start` / `on_chain_end`                 | opens/closes `span()`             |
    | `on_llm_start` / `on_llm_end`                     | `.action()` / `.observation()`    |
    | `on_agent_action`                                 | `.action()`                       |
    | `on_agent_finish`                                 | `.decision()`                     |
    | `on_tool_start`/`on_tool_end`/`on_tool_error`     | `.action()`/`.observation()`/`.error()` |

    LangChain's own `run_id`/`parent_run_id` are written directly onto
    `meta.span_id`/`meta.parent_span_id` — the shapes already match, so this
    is field renaming, not translation.
    """

    def __init__(self, agent_log: Logger) -> None:
        LogQuillAdapter.__init__(self, agent_log)
        BaseCallbackHandler.__init__(self)
        self._open_spans: dict[UUID, SpanContext] = {}
        self._call_starts: dict[UUID, float] = {}

    def _duration_ms(self, run_id: UUID) -> float | None:
        start = self._call_starts.pop(run_id, None)
        if start is None:
            return None
        return round((time.monotonic() - start) * 1000, 3)

    # -- chains: each chain run opens/closes a span ----------------------

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        name = _tool_name(serialized, "chain")
        span = self.log.span(
            name,
            span_id=str(run_id),
            parent_span_id=str(parent_run_id) if parent_run_id is not None else None,
        )
        span.__enter__()
        self._open_spans[run_id] = span

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        span = self._open_spans.pop(run_id, None)
        if span is not None:
            span.__exit__(None, None, None)

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        span = self._open_spans.pop(run_id, None)
        if span is not None:
            span.__exit__(type(error), error, error.__traceback__)

    # -- LLM calls: action (start) / observation (end) --------------------

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        self._call_starts[run_id] = time.monotonic()
        self.log.action("llm_start", **_span_ids(run_id, parent_run_id))

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        duration_ms = self._duration_ms(run_id)
        meta = _span_ids(run_id, parent_run_id)
        if duration_ms is not None:
            meta["duration_ms"] = duration_ms
        self.log.observation("llm_end", **meta)

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        self._duration_ms(run_id)
        self.log.error("llm_error", error=str(error), **_span_ids(run_id, parent_run_id))

    # -- agent-level events -------------------------------------------------

    # `on_agent_action`/`on_agent_finish` carry the *enclosing* chain's own
    # `run_id` (LangChain doesn't mint a fresh one for these events) — unlike
    # `on_llm_start`/`on_tool_start`, mapping it onto `span_id` here would
    # make the record its own parent, since that same id is already the
    # active span pushed by the enclosing `on_chain_start`. Leaving span
    # kwargs unset lets `Logger._log`'s ambient-span auto-stamp supply the
    # correct `parent_span_id` instead.

    def on_agent_action(
        self,
        action: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        tool = getattr(action, "tool", "agent_action")
        self.log.action(tool)

    def on_agent_finish(
        self,
        finish: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        self.log.decision("agent_finish")

    # -- tools: action (start) / observation (end) / error ------------------

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        name = _tool_name(serialized, "tool")
        self._call_starts[run_id] = time.monotonic()
        self.log.action(name, **_span_ids(run_id, parent_run_id))

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        duration_ms = self._duration_ms(run_id)
        meta = _span_ids(run_id, parent_run_id)
        if duration_ms is not None:
            meta["duration_ms"] = duration_ms
        self.log.observation("tool_end", **meta)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        self._duration_ms(run_id)
        self.log.error("tool_error", error=str(error), **_span_ids(run_id, parent_run_id))
