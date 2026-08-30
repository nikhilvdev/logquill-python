from __future__ import annotations

import json
from typing import Protocol, Sequence, cast

from logquill.formatter import Formatter
from logquill.records import LogRecord
from logquill.transports.queue.base_queue_transport import BaseQueueTransport


class AMQPChannelLike(Protocol):
    def basic_publish(self, exchange: str, routing_key: str, body: bytes) -> object: ...


class AMQPConnectionLike(Protocol):
    def close(self) -> None: ...


class RabbitMQTransport(BaseQueueTransport):
    """Publishes to RabbitMQ via the optional `pika` peer dependency. One
    `basic_publish` call per record on the default exchange (AMQP has no
    native multi-message batch form). Pass `channel` to inject a pre-built
    `pika` channel (or a fake, for tests), or `url` to let this transport
    connect itself."""

    def __init__(
        self,
        *,
        topic: str,
        channel: AMQPChannelLike | None = None,
        url: str = "amqp://guest:guest@localhost:5672/%2F",
        formatter: Formatter | None = None,
        max_records: int = 100,
        max_bytes: int = 1_000_000,
    ) -> None:
        super().__init__(
            topic=topic, formatter=formatter, max_records=max_records, max_bytes=max_bytes
        )
        self._injected = channel
        self._url = url
        self._channel: AMQPChannelLike | None = None
        self._connection: AMQPConnectionLike | None = None

    def _resolved_channel(self) -> AMQPChannelLike:
        if self._injected is not None:
            return self._injected
        if self._channel is None:
            self._channel = self._import_channel()
        return self._channel

    def _import_channel(self) -> AMQPChannelLike:
        try:
            import pika  # type: ignore  # stub availability for this optional dep varies by env
        except ImportError as exc:
            raise ImportError(
                "RabbitMQTransport: install `pika` to use this transport "
                "without providing a channel — `pip install logquill[rabbitmq]`"
            ) from exc
        connection = pika.BlockingConnection(pika.URLParameters(self._url))
        self._connection = cast(AMQPConnectionLike, connection)
        channel = connection.channel()
        channel.queue_declare(queue=self.topic)
        return cast(AMQPChannelLike, channel)

    def close(self) -> None:
        super().close()
        if self._injected is None and self._connection is not None:
            self._connection.close()

    def _publish_batch(self, records: Sequence[LogRecord]) -> None:
        channel = self._resolved_channel()
        for record in records:
            body = json.dumps(record, separators=(",", ":"), default=str).encode("utf-8")
            channel.basic_publish(exchange="", routing_key=self.topic, body=body)
