from __future__ import annotations

import json
from typing import Protocol, Sequence, cast

from logquill.formatter import Formatter
from logquill.records import LogRecord
from logquill.transports.queue.base_queue_transport import BaseQueueTransport


class KafkaProducerLike(Protocol):
    def send(self, topic: str, value: bytes, key: bytes | None = None) -> object: ...
    def flush(self) -> None: ...
    def close(self) -> None: ...


def _partition_key(record: LogRecord) -> bytes | None:
    meta = record["meta"]
    run_id = meta.get("run_id")
    if isinstance(run_id, str) and run_id:
        return run_id.encode("utf-8")
    trace_id = meta.get("trace_id")
    if isinstance(trace_id, str) and trace_id:
        return trace_id.encode("utf-8")
    return None


class KafkaTransport(BaseQueueTransport):
    """Publishes batches to Kafka via the optional `kafka-python` peer
    dependency (pure Python — no `librdkafka` system dependency, unlike
    `confluent-kafka`), keyed by `meta["run_id"]`/`meta["trace_id"]` so one
    trace's records stay ordered on the same partition. Pass `producer` to
    inject a pre-built `KafkaProducer` (or a fake, for tests), or
    `bootstrap_servers` to let this transport connect itself."""

    def __init__(
        self,
        *,
        topic: str,
        producer: KafkaProducerLike | None = None,
        bootstrap_servers: str = "localhost:9092",
        formatter: Formatter | None = None,
        max_records: int = 100,
        max_bytes: int = 1_000_000,
    ) -> None:
        super().__init__(
            topic=topic, formatter=formatter, max_records=max_records, max_bytes=max_bytes
        )
        self._injected = producer
        self._bootstrap_servers = bootstrap_servers
        self._producer: KafkaProducerLike | None = None

    def _resolved_producer(self) -> KafkaProducerLike:
        if self._injected is not None:
            return self._injected
        if self._producer is None:
            self._producer = self._import_producer()
        return self._producer

    def _import_producer(self) -> KafkaProducerLike:
        try:
            import kafka  # type: ignore  # stub availability for this optional dep varies by env
        except ImportError as exc:
            raise ImportError(
                "KafkaTransport: install `kafka-python` to use this "
                "transport without providing a producer — "
                "`pip install logquill[kafka]`"
            ) from exc
        return cast(
            KafkaProducerLike, kafka.KafkaProducer(bootstrap_servers=self._bootstrap_servers)
        )

    def close(self) -> None:
        super().close()
        if self._injected is None and self._producer is not None:
            self._producer.close()

    def _publish_batch(self, records: Sequence[LogRecord]) -> None:
        producer = self._resolved_producer()
        for record in records:
            value = json.dumps(record, separators=(",", ":"), default=str).encode("utf-8")
            producer.send(self.topic, value=value, key=_partition_key(record))
        producer.flush()
