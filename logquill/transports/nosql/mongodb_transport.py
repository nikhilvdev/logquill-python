from __future__ import annotations

from typing import Any, Protocol, Sequence, cast

from logquill.formatter import Formatter
from logquill.records import LogRecord
from logquill.transports.batching_transport import BatchingTransport


class MongoCollectionLike(Protocol):
    def insert_many(self, documents: Sequence[dict[str, Any]]) -> object: ...


class MongoClientLike(Protocol):
    def close(self) -> None: ...


class MongoDBTransport(BatchingTransport[LogRecord]):
    """Batches log records into `insert_many()` calls against a MongoDB
    collection — records map 1:1 to documents, no JSON-in-a-column
    workaround needed. Pass `collection` to inject a pre-built
    `pymongo.Collection` (or a fake, for tests), or `uri`/`database`/
    `collection_name` to let this transport connect itself via the
    optional `pymongo` peer dependency."""

    def __init__(
        self,
        *,
        collection: MongoCollectionLike | None = None,
        uri: str = "mongodb://localhost:27017",
        database: str = "logquill",
        collection_name: str = "logs",
        formatter: Formatter | None = None,
        max_records: int = 100,
        max_bytes: int = 1_000_000,
    ) -> None:
        super().__init__(formatter=formatter, max_records=max_records, max_bytes=max_bytes)
        self._injected = collection
        self._uri = uri
        self._database = database
        self._collection_name = collection_name
        self._collection: MongoCollectionLike | None = None
        self._client: MongoClientLike | None = None

    def _resolved_collection(self) -> MongoCollectionLike:
        if self._injected is not None:
            return self._injected
        if self._collection is None:
            self._collection = self._import_collection()
        return self._collection

    def _import_collection(self) -> MongoCollectionLike:
        try:
            import pymongo  # type: ignore  # stub availability for this optional dep varies by env
        except ImportError as exc:
            raise ImportError(
                "MongoDBTransport: install `pymongo` to use this transport "
                "without providing a collection — `pip install logquill[mongodb]`"
            ) from exc
        client = pymongo.MongoClient(self._uri)
        self._client = cast(MongoClientLike, client)
        return cast(MongoCollectionLike, client[self._database][self._collection_name])

    def close(self) -> None:
        super().close()
        if self._injected is None and self._client is not None:
            self._client.close()

    def _send_batch(self, batch: Sequence[LogRecord]) -> None:
        collection = self._resolved_collection()
        collection.insert_many([dict(record) for record in batch])
