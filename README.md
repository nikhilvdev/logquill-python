# logquill

[![CI](https://github.com/nikhilvdev/logquill-python/actions/workflows/ci.yml/badge.svg)](https://github.com/nikhilvdev/logquill-python/actions/workflows/ci.yml)
[![Publish](https://github.com/nikhilvdev/logquill-python/actions/workflows/release.yml/badge.svg)](https://github.com/nikhilvdev/logquill-python/actions/workflows/release.yml)
[![PyPI](https://img.shields.io/pypi/v/logquill.svg)](https://pypi.org/project/logquill/)
[![Python versions](https://img.shields.io/badge/python-3.8%2B-blue.svg)](pyproject.toml)
[![License](https://img.shields.io/github/license/nikhilvdev/logquill-python)](LICENSE)
[![GitHub tag](https://img.shields.io/github/v/tag/nikhilvdev/logquill-python)](https://github.com/nikhilvdev/logquill-python/tags)
[![Downloads](https://static.pepy.tech/badge/logquill)](https://pepy.tech/project/logquill)

A structured, leveled logging framework for Python with pluggable transports.
Sibling to [`logquill` on npm](https://www.npmjs.com/package/logquill)
(`logquill-js`) — same log record shape, same level names, one mental model
across a Python + Node stack.

Status: pre-release, under active development. The core `Logger`, level
filtering, transports, and the plugin pipeline are implemented;
non-blocking async dispatch is not yet — see `CHANGELOG.md` for what's
landed so far.

## Features

- **Structured by default** — every call carries a `meta` dict, not just a message string
- **Cross-language record shape** — identical JSON shape and level names/weights as [`logquill` on npm](https://www.npmjs.com/package/logquill)
- **Pluggable transports** — `ConsoleTransport` (colorized, stderr for errors), `FileTransport` (rotation), `HTTPTransport` (batched), plus SQL/NoSQL/message-queue/cloud-native sinks (see [Transports](#transports)); write your own by subclassing `Transport`
- **Pluggable formatters** — `JSONFormatter` out of the box; implement `format(record) -> str` for your own
- **Plugin pipeline** — `ContextPlugin`, `RedactPlugin`, `SamplingPlugin` out of the box; a broken plugin can't crash logging
- **Zero required runtime dependencies** — stdlib only; `aiohttp` is opt-in, for async HTTP
- **Typed throughout** — `mypy --strict` clean on the public API
- *(planned)* non-blocking async dispatch, `contextvars`-based context propagation — see `CHANGELOG.md`

## Install

```bash
pip install logquill
```

## Quickstart

```python
from logquill import Level, Logger

logger = Logger("app", level=Level.INFO)

record = logger.info("user signed up", user_id=42, plan="pro")
print(record)
# {'timestamp': '2026-08-27T18:04:12.345Z', 'level': 'INFO', 'logger': 'app',
#  'message': 'user signed up', 'meta': {'user_id': 42, 'plan': 'pro'}}

logger.debug("below threshold, dropped")  # -> None, filtered by level
logger.set_level("debug")
logger.debug("now visible")  # -> a record dict
```

Every log call returns the record dict (or `None` if filtered by level) —
`{"timestamp": ISO8601, "level": str, "logger": str, "message": str, "meta": dict}`,
the same shape shared with [`logquill` on npm](https://www.npmjs.com/package/logquill).
Use `JSONFormatter` to serialize a record to the canonical JSON line:

```python
from logquill import JSONFormatter

print(JSONFormatter().format(record))
# '{"timestamp":"2026-08-27T18:04:12.345Z","level":"INFO","logger":"app","message":"user signed up","meta":{"user_id":42,"plan":"pro"}}'
```

## Transports

Attach transports to a `Logger` to actually write records somewhere. Each
record is dispatched to every attached transport synchronously (non-blocking
dispatch isn't implemented yet):

```python
from logquill import ConsoleTransport, FileTransport, HTTPTransport, Logger

logger = Logger(
    "app",
    transports=[
        ConsoleTransport(),  # stdout, ERROR/FATAL to stderr, colorized
        FileTransport("app.log", max_bytes=10 * 1024 * 1024, backup_count=5),
        HTTPTransport("https://logs.example.com/ingest", batch_size=50),
    ],
)

logger.info("user signed up", user_id=42, plan="pro")
logger.close()  # flushes the file handle and any buffered HTTP batch
```

Write your own transport by subclassing `Transport` and implementing
`write(formatted, record)`; `format(record)` and `close()` have sensible
defaults. `CollectingTransport` is a ready-made in-memory transport, handy
in your own tests:

```python
from logquill import CollectingTransport, Logger

sink = CollectingTransport()
logger = Logger("app.test", transports=[sink])

logger.info("hello")
assert sink.records[0]["message"] == "hello"
```

### SQL, NoSQL, message queue, and cloud-native transports

Every transport below shares one design: records are **always batched**
(bounded by both count and estimated byte size via a shared
`BatchingTransport` base — never one write per log call), and every
optional backend driver is a **lazy, injectable dependency** — pass a
pre-built client/connection for tests or an alternate setup, or let the
transport construct one itself from the real driver on first use. A
missing driver raises an actionable `ImportError` telling you which
extra to install, the same shape every transport in this list follows.

`SQLiteTransport` needs no optional dependency at all (stdlib `sqlite3`),
so it's fully runnable as-is:

```python
from logquill import Logger, SQLiteTransport

transport = SQLiteTransport(filename="app.db", ensure_schema=True, max_records=100)
logger = Logger("app", transports=[transport])

logger.info("user signed up", user_id=42, run_id="run-1")
logger.close()  # flushes any buffered rows
```

Every other backend follows the same injection shape — here's
`MongoDBTransport` with a hand-rolled fake standing in for a real
`pymongo` collection (the same pattern every transport's own test suite
uses, so you never need a live service to test your own logging setup):

```python
from logquill import Logger, MongoDBTransport

class FakeCollection:
    def __init__(self):
        self.documents = []
    def insert_many(self, documents):
        self.documents.extend(documents)

collection = FakeCollection()
transport = MongoDBTransport(collection=collection, max_records=1)
logger = Logger("app", transports=[transport])

logger.info("user signed up", user_id=42)
assert collection.documents[0]["message"] == "user signed up"
```

Passing a real `pymongo.Collection` instead of a fake works identically —
`MongoDBTransport(uri="mongodb://localhost:27017", database="app", collection_name="logs")`
builds one lazily via the optional `pymongo` peer dependency.

**SQL** — `BaseSQLTransport` (a fixed `logs` table: `timestamp`/`level`/
`logger`/`message`/`meta`, plus `run_id`/`span_id`/`parent_span_id`/
`trace_id` for upcoming cross-service trace-correlation support).
`ensure_schema=True` is a dev/test convenience only — production
schema/migrations are your responsibility, same as every batching
transport below.

| Transport | Driver | Extra |
|---|---|---|
| `SQLiteTransport` | stdlib `sqlite3` | *(none)* |
| `PostgresTransport` | `psycopg2-binary` | `pip install logquill[postgres]` |
| `MySQLTransport` | `pymysql` | `pip install logquill[mysql]` |

**NoSQL**

| Transport | Driver | Extra |
|---|---|---|
| `MongoDBTransport` | `pymongo` | `pip install logquill[mongodb]` |
| `DynamoDBTransport` | `boto3` | `pip install logquill[aws]` |
| `RedisTransport` | `redis` | `pip install logquill[redis]` |

`DynamoDBTransport` partitions by `meta["run_id"]` (falling back to
`meta["trace_id"]`, then the logger name) with `timestamp` as the sort
key. `RedisTransport` writes to a Redis Stream via `XADD` — a fast local
buffer/tail, not a durable store.

**Message queues** — `BaseQueueTransport` (`topic` names the Kafka
topic / RabbitMQ queue / SQS queue URL / GCP Pub/Sub topic path).
Decouples log producers from consumers so a SIEM, an analytics pipeline,
and an alerting system can all fan out from one topic. `SQSTransport`
chunks at the API's 10-message `SendMessageBatch` cap:

```python
from logquill import Logger, SQSTransport

class FakeSQSClient:
    def __init__(self):
        self.calls = []
    def send_message_batch(self, QueueUrl, Entries):
        self.calls.append((QueueUrl, Entries))

client = FakeSQSClient()
transport = SQSTransport(
    topic="https://sqs.us-east-1.amazonaws.com/123456789012/app-logs",
    client=client,
    max_records=12,
)
logger = Logger("app", transports=[transport])
for i in range(12):
    logger.info(f"event {i}")
# chunked into two send_message_batch calls: 10 messages, then 2
```

| Transport | Driver | Extra |
|---|---|---|
| `KafkaTransport` | `kafka-python` | `pip install logquill[kafka]` |
| `RabbitMQTransport` | `pika` | `pip install logquill[rabbitmq]` |
| `SQSTransport` | `boto3` | `pip install logquill[aws]` |
| `PubSubTransport` | `google-cloud-pubsub` | `pip install logquill[pubsub]` |

**Cloud-native** — `DatadogTransport`, `ElasticsearchTransport`, and
`AppInsightsTransport` need no client SDK at all: each POSTs directly to
its provider's public ingestion endpoint via stdlib `urllib`, with an
injectable `sender` for tests:

```python
from logquill import DatadogTransport, Logger

class FakeSender:
    def __init__(self):
        self.calls = []
    def __call__(self, url, api_key, batch):
        self.calls.append((url, api_key, batch))

sender = FakeSender()
transport = DatadogTransport(api_key="dd-api-key", sender=sender, max_records=1)
logger = Logger("app", transports=[transport])

logger.info("user signed up", user_id=42)
```

| Transport | Mechanism | Extra |
|---|---|---|
| `CloudWatchTransport` | `boto3` | `pip install logquill[aws]` |
| `CloudLoggingTransport` | `google-cloud-logging` | `pip install logquill[gcp-logging]` |
| `AppInsightsTransport` | stdlib `urllib` (public ingestion endpoint) | *(none)* |
| `DatadogTransport` | stdlib `urllib` | *(none)* |
| `ElasticsearchTransport` | stdlib `urllib` (`_bulk` API) | *(none)* |
| `NewRelicTransport` | stdlib `urllib` + `gzip` | *(none)* |

`NewRelicTransport` gzips every payload, strips `meta["eventType"]` (New
Relic's reserved key), and on a `429` response reads `Retry-After` and
pauses sends until it elapses — dropping (not requeuing) any batch
flushed during that window, since New Relic blocks the rest of that
minute on a rate-limit breach anyway.

## Plugins

Plugins hook into the pipeline around each log call: `before_log(record)` can
transform a record or return `None` to drop it, `after_log(record)` runs once
it's been dispatched to every transport, and `on_error(exc, record)` catches
anything a plugin's own hooks raise — a broken plugin can't take down logging.

```python
from logquill import ContextPlugin, Logger, RedactPlugin, SamplingPlugin

logger = Logger("app")
logger.use(ContextPlugin(service="api", env="prod"))  # merged into every record's meta
logger.use(RedactPlugin(keys=["password", "token"]))  # replaces matching meta values
logger.use(SamplingPlugin(0.1))  # keep ~10% of records that reach this point

logger.info("login attempt", user_id=42, password="hunter2")
# meta: {'service': 'api', 'env': 'prod', 'user_id': 42, 'password': '***'}
# (unless this call was one of the ~90% sampling dropped, in which case it's None)
```

Write your own by subclassing `Plugin`; override only the hooks you need.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,http,hooks]"
pre-commit install

ruff check .
mypy logquill
pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the PR workflow, the
[Code of Conduct](CODE_OF_CONDUCT.md) for community standards, and
[SECURITY.md](.github/SECURITY.md) for how to report a vulnerability.
