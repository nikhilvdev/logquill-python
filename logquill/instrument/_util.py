"""Shared plumbing for the `logquill.instrument.*` patchers: swap one method
or function out for a wrapper, remember how to put it back, and never let a
bug in the wrapper break the real call it wraps.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

_logger = logging.getLogger("logquill")

T = TypeVar("T")


@dataclass
class Patch:
    """One reversible attribute swap."""

    target: Any
    name: str
    original: Any

    def revert(self) -> None:
        """Puts `original` back."""
        setattr(self.target, self.name, self.original)


def apply(target: Any, name: str, build_wrapper: Callable[[Any], Any]) -> Patch:
    """Replaces `target.name` with `build_wrapper(current_value)` and returns
    a `Patch` that can put it back."""
    original = getattr(target, name)
    setattr(target, name, build_wrapper(original))
    return Patch(target, name, original)


def record_safely(do_record: Callable[[], None]) -> None:
    """Runs `do_record` (which logs one call's fields), swallowing and
    logging any exception. A bug in instrumentation must never surface as a
    failure of the API call it's instrumenting — the whole point of
    `instrument()` is that call sites don't change, including their error
    handling."""
    try:
        do_record()
    except Exception:
        _logger.exception("logquill.instrument: failed to record a call")


class Instrumenter:
    """One `logquill.instrument.<provider>` entry: calling it patches,
    `.uninstrument()` puts everything back. Calling it twice without an
    intervening `.uninstrument()` raises, so a wrapper is never wrapped
    twice — each instrumented method would otherwise fire this provider's
    `llm_call` twice per real call, once per layer.
    """

    def __init__(self, name: str, apply_patches: Callable[..., list[Patch]]) -> None:
        """`name` is used only in the "already active" error message.
        `apply_patches` does the actual patching (typically importing the
        provider SDK lazily and calling `apply()` once per method) and
        returns the `Patch`es to revert later."""
        self._name = name
        self._apply_patches = apply_patches
        self._patches: list[Patch] = []

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        """Patches the provider SDK. See the concrete module (e.g.
        `logquill.instrument.anthropic`) for what arguments it takes."""
        if self._patches:
            raise RuntimeError(
                f"logquill.instrument.{self._name} is already active — call "
                f".uninstrument() first if you want to change its logger or options"
            )
        self._patches = self._apply_patches(*args, **kwargs)

    def uninstrument(self) -> None:
        """Restores every method this patched. Safe to call even when not
        currently instrumented."""
        while self._patches:
            self._patches.pop().revert()

    @property
    def active(self) -> bool:
        """Whether `instrument()` has been called without a matching
        `.uninstrument()` since."""
        return bool(self._patches)
