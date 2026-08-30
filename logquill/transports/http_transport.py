from __future__ import annotations

import urllib.request
from typing import Callable, Sequence

from logquill.formatter import Formatter
from logquill.records import LogRecord
from logquill.transports.transport import Transport

Sender = Callable[[str, Sequence[str]], None]


def _urllib_sender(url: str, batch: Sequence[str]) -> None:
    body = "\n".join(batch).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-ndjson"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
        response.read()


class HTTPTransport(Transport):
    """Batches formatted records and POSTs them as newline-delimited JSON.

    Uses `urllib` (stdlib) by default so the core package stays dependency-free.
    Pass `sender` to swap in a fake for tests, or a different backend (e.g. an
    aiohttp-based one, once a non-blocking async dispatch path exists).
    """

    def __init__(
        self,
        url: str,
        *,
        formatter: Formatter | None = None,
        batch_size: int = 50,
        sender: Sender | None = None,
    ) -> None:
        super().__init__(formatter)
        self.url = url
        self.batch_size = batch_size
        self._sender: Sender = sender or _urllib_sender
        self._batch: list[str] = []

    def write(self, formatted: str, record: LogRecord) -> None:
        self._batch.append(formatted)
        if len(self._batch) >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        if not self._batch:
            return
        batch, self._batch = self._batch, []
        self._sender(self.url, batch)

    def close(self) -> None:
        self.flush()
