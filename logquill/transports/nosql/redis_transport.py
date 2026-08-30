from __future__ import annotations

import json
from typing import Any, Protocol, Sequence

from logquill.formatter import Formatter
from logquill.records import LogRecord
from logquill.transports.batching_transport import BatchingTransport


class RedisClientLike(Protocol):
    def xadd(self, name: str, fields: dict[str, Any]) -> object: ...
    def close(self) -> None: ...


class RedisTransport(BatchingTransport[LogRecord]):
    """Appends each record to a Redis Stream via `XADD`, through the
    optional `redis` peer dependency — a fast local buffer/tail, **not** a
    durable store, worth using as such rather than as a replacement for a
    SQL/NoSQL sink. One `XADD` per record: Streams has no native
    multi-record batch form, unlike `SendMessageBatch`/`BatchWriteItem`.
    Pass `client` to inject a pre-built `redis.Redis` (or a fake, for
    tests), or `url` to let this transport connect itself."""

    def __init__(
        self,
        *,
        client: RedisClientLike | None = None,
        stream: str = "logs",
        url: str = "redis://localhost:6379",
        formatter: Formatter | None = None,
        max_records: int = 100,
        max_bytes: int = 1_000_000,
    ) -> None:
        super().__init__(formatter=formatter, max_records=max_records, max_bytes=max_bytes)
        self._injected = client
        self._stream = stream
        self._url = url
        self._client: RedisClientLike | None = None

    def _resolved_client(self) -> RedisClientLike:
        if self._injected is not None:
            return self._injected
        if self._client is None:
            self._client = self._import_client()
        return self._client

    def _import_client(self) -> RedisClientLike:
        try:
            import redis  # type: ignore  # stub availability for this optional dep varies by env
        except ImportError as exc:
            raise ImportError(
                "RedisTransport: install `redis` to use this transport "
                "without providing a client — `pip install logquill[redis]`"
            ) from exc
        client: RedisClientLike = redis.Redis.from_url(self._url)
        return client

    def close(self) -> None:
        super().close()
        if self._injected is None and self._client is not None:
            self._client.close()

    def _send_batch(self, batch: Sequence[LogRecord]) -> None:
        client = self._resolved_client()
        for record in batch:
            client.xadd(
                self._stream,
                {
                    "timestamp": record["timestamp"],
                    "level": record["level"],
                    "logger": record["logger"],
                    "message": record["message"],
                    "meta": json.dumps(record["meta"], separators=(",", ":"), default=str),
                },
            )
