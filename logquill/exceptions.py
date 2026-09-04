from __future__ import annotations

import sys
import traceback
from types import TracebackType
from typing import Literal, Union

# `Literal[True]` rather than `bool`: `False` behaves identically to `None`
# (both mean "nothing to format", handled by the `not exc_info` check below),
# so it isn't a distinct case worth widening the type for — and keeping it
# out lets the branches below narrow cleanly under `mypy --strict`.
ExcInfoArg = Union[
    Literal[True],
    BaseException,
    "tuple[type[BaseException], BaseException, TracebackType | None]",
    None,
]


def format_exc_info(exc_info: ExcInfoArg) -> str | None:
    """Render `exc_info` as a formatted traceback string, or `None` if
    there's nothing to format. Accepts the same shapes stdlib `logging`
    does, so `logger.error("failed", exc_info=e)` reads exactly like the
    `logging` module's own `exc_info=` kwarg:

    - `True` — format the exception currently being handled (`sys.exc_info()`)
    - an exception instance — format it and its own traceback
    - an explicit `(type, value, traceback)` tuple
    - falsy (`False`/`None`, the default) — nothing to format
    """
    if not exc_info:
        return None

    exc_type: type[BaseException] | None
    exc_value: BaseException | None
    exc_tb: TracebackType | None

    if exc_info is True:
        exc_type, exc_value, exc_tb = sys.exc_info()
        if exc_type is None:
            return None
    elif isinstance(exc_info, BaseException):
        exc_type, exc_value, exc_tb = type(exc_info), exc_info, exc_info.__traceback__
    else:
        exc_type, exc_value, exc_tb = exc_info

    return "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
