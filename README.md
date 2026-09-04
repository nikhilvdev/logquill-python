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
filtering, transports, the plugin pipeline, and agentic/harness tracing are
implemented; non-blocking async dispatch is not yet — see `CHANGELOG.md`
for what's landed so far.

## Features

- **Structured by default** — every call carries a `meta` dict, not just a message string
- **Cross-language record shape** — identical JSON shape and level names/weights as [`logquill` on npm](https://www.npmjs.com/package/logquill)
- **Pluggable transports** — `ConsoleTransport` (colorized, stderr for errors), `FileTransport` (rotation, optional encryption-at-rest), `HTTPTransport` (batched), `SyslogTransport` (RFC 5424, UDP/TCP), plus SQL/NoSQL/message-queue/cloud-native sinks (see [Transports](#transports)); write your own by subclassing `Transport`
- **Pluggable formatters** — `JSONFormatter` out of the box; implement `format(record) -> str` for your own
- **Config from file/env** — `load_config(dict)`, `logger_from_file(path)` (JSON/YAML), `logger_from_env()` build a `Logger` from one config shape — see [Config](#config)
- **Plugin pipeline** — `ContextPlugin`, `RedactPlugin` (by key), `PIIRedactPlugin` (by pattern), `SamplingPlugin` (with tail-based elevation), `TamperEvidentPlugin` (hash-chained logs), `TraceContextPlugin` (cross-service trace correlation), and `AlertingPlugin` (`SlackAlertPlugin`/`PagerDutyAlertPlugin`/`EmailAlertPlugin`, deduplicated) out of the box; a broken plugin can't crash logging; `.use()` also accepts a plain function, no subclassing required (see [Plugins](#plugins))
- **Agentic & harness tracing** — `.child()` loggers, `RunPlugin`, `.thought()/.action()/.observation()/.decision()`, `with agent_log.span(...)`, and framework adapters — `LangChainAdapter` (`pip install logquill[langchain]`), `LangGraphAdapter` (`pip install logquill[langgraph]`, adds checkpoint interrupt/resume events on top), `CrewAIAdapter` (`pip install logquill[crewai]`), `LlamaIndexAdapter` (`pip install logquill[llamaindex]`), and `AutoGenAdapter` (`pip install logquill[autogen]`) — see [Agentic & harness tracing](#agentic--harness-tracing)
- **Non-blocking async dispatch** — `Logger(async_dispatch=True)` moves transport writes onto a background thread with a bounded queue and a configurable backpressure policy (`drop_oldest`/`drop_newest`/`block`); `flush()`/`flush_async()` and a `with_lambda`/`with_cloud_function`/`with_azure_function` decorator make serverless shutdown safe — see [Async dispatch & serverless safety](#async-dispatch--serverless-safety)
- **Zero required runtime dependencies** — stdlib only; `aiohttp` is opt-in, for async HTTP
- **Typed throughout** — `mypy --strict` clean on the public API
- **Context propagation, exception capture & the stdlib bridge** — `bind_context()` (`contextvars`-based, no manual passing), `exc_info=` on any `Logger` method (formatted traceback into `meta["stack"]`), `LogQuillHandler` (bridges stdlib `logging` into a `Logger`), and `RateLimitPlugin` — see [Context propagation, exception capture & the stdlib bridge](#context-propagation-exception-capture--the-stdlib-bridge)

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

## Config

Build a `Logger` from a config dict, a JSON/YAML file, or the environment,
instead of wiring transports/plugins up by hand — the same shape across all
three:

```python
from logquill import load_config

logger = load_config({
    "name": "app",
    "level": "INFO",
    "transports": [{"type": "console"}],
    "plugins": [{"type": "context", "options": {"service": "api", "env": "prod"}}],
})
logger.info("ready")
```

```python
from logquill import logger_from_file

logger = logger_from_file("config.json")  # or config.yaml — needs `pip install logquill[yaml]`
```

```python
import os
from logquill import logger_from_env

os.environ["LOGQUILL_CONFIG_FILE"] = "config.json"
os.environ["LOGQUILL_LEVEL"] = "DEBUG"  # always overrides the file's level

logger = logger_from_env()  # prefix defaults to "LOGQUILL_"
```

A small built-in `"type"` registry covers the zero-dependency transports/
plugins (`console`, `file`, `http`; `context`, `redact`, `sampling`,
`trace_context`, `run`, `pii_redact`, `tamper_evident`). Anything else —
every cloud/SQL/NoSQL/queue transport, the alerting plugins, a framework
adapter, or your own subclass — goes through `"class"` instead, a
fully-qualified dotted path resolved the same way `logging.config.
dictConfig` resolves one:

```python
from logquill import load_config

logger = load_config({
    "transports": [
        {
            "class": "logquill.transports.cloud.datadog_transport.DatadogTransport",
            "options": {"api_key": "..."},
        }
    ],
})
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

`SyslogTransport` sends each record as one RFC 5424 message over UDP
(default) or TCP — stdlib `socket` only, no dependency, and not a batching
transport (syslog is one-message-per-call, unlike the HTTP-API transports
above):

```python
from logquill import Logger, SyslogTransport

transport = SyslogTransport(host="syslog.internal", port=514, app_name="app")
logger = Logger("app", transports=[transport])

logger.error("payment webhook failed")
```

### Encryption-at-rest for file logs

`FileTransport(encrypt_key=...)` encrypts each line with
`cryptography.fernet.Fernet` before writing — a local log file usually
isn't encrypted server-side the way a cloud sink already is:

```python
from cryptography.fernet import Fernet
from logquill import FileTransport, Logger

key = Fernet.generate_key()  # store this somewhere safe — you need it to decrypt
transport = FileTransport("app.log", encrypt_key=key)
logger = Logger("app", transports=[transport])

logger.info("card charged", user_id=42)
logger.close()

# decrypt back, one Fernet token per line
fernet = Fernet(key)
with open("app.log", "rb") as f:
    for line in f:
        print(fernet.decrypt(line.strip()).decode("utf-8"))
```

Needs the optional `cryptography` dependency (`pip install
logquill[crypto]`), imported lazily — `FileTransport` has zero
dependencies as long as `encrypt_key` stays unset.

## Plugins

Plugins hook into the pipeline around each log call: `before_log(record)` can
transform a record or return `None` to drop it, `after_log(record)` runs once
it's been dispatched to every transport, and `on_error(exc, record)` catches
anything a plugin's own hooks raise — a broken plugin can't take down logging.
Records are **not** deep-copied through the pipeline — a plugin receives and
may mutate the same dict every other plugin sees; copy it yourself in
`before_log` if you need to preserve the original.

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

Write your own by subclassing `Plugin`; override only the hooks you need. For
a one-off transform, skip the subclass entirely — `.use()` also accepts a
plain function, wrapped internally as an anonymous `Plugin`:

```python
from logquill import Logger

def strip_ssn(record):
    record["meta"].pop("ssn", None)
    return record  # or None to drop the record

logger = Logger("app")
logger.use(strip_ssn)
logger.info("submit", ssn="123-45-6789", user_id=42)
# meta: {'user_id': 42}
```

### Tail-based sampling elevation

Plain `SamplingPlugin(rate)` drops records independently of each other. Add
`transports=` and every record's `meta["trace_id"]` (configurable via
`trace_key`) turns sampling tail-based instead: a dropped record is buffered
under its trace id rather than discarded, and if any later record in that
same trace reaches `elevate_at` (default `ERROR`), the whole trace — every
buffered record plus everything from then on — ships, flushed straight to
`transports`. A request that looked unremarkable when it started still
produces a complete trace once it turns out to have failed.

```python
from logquill import CollectingTransport, Logger, SamplingPlugin

sink = CollectingTransport()
sampling = SamplingPlugin(0.01, transports=[sink])  # keep ~1%, tail-elevate the rest
logger = Logger("app", transports=[sink], plugins=[sampling])

logger.info("received request", trace_id="req-42")   # likely dropped — held in the buffer
logger.info("queried database", trace_id="req-42")    # likely dropped — held in the buffer
logger.error("query timed out", trace_id="req-42")     # elevates the whole trace

assert [r["message"] for r in sink.records] == [
    "received request",
    "queried database",
    "query timed out",
]
```

Buffering is bounded by `max_buffered_records` and `max_traces` — the oldest
buffered trace is evicted once either limit is hit, so a single
high-cardinality or long-lived trace can't grow memory without limit.

### PII redaction by pattern, not just key

`RedactPlugin` redacts by exact key match. `PIIRedactPlugin` complements it by
scanning `meta` **values** — recursively through nested dicts/lists/tuples —
for emails, SSNs, credit-card numbers, and phone numbers, and redacts matches
wherever they appear, regardless of which key holds them:

```python
from logquill import Logger, PIIRedactPlugin

logger = Logger("app", plugins=[PIIRedactPlugin()])

logger.info("support ticket", notes="reach me at jane@example.com, ssn 123-45-6789")
# meta: {'notes': 'reach me at ***, ssn ***'}
```

Detection is regex-based by default — fast, dependency-free, matched on shape
rather than meaning. For fuzzier ML-based detection instead, pass
`use_presidio=True` (`pip install logquill[presidio]`) to route values
through Microsoft Presidio's analyzer/anonymizer; Presidio stays a real,
opt-in dependency, never a default one.

### Tamper-evident logs

`TamperEvidentPlugin` hash-chains every record — each one's `meta.hash` covers
its own content plus the previous record's hash — so editing, removing, or
reordering a line in a written log breaks the chain from that point on.
Opt-in, since hashing every record has a real CPU cost:

```python
from logquill import Logger, TamperEvidentPlugin

logger = Logger("app", plugins=[TamperEvidentPlugin()])
records = [logger.info(f"step {i}") for i in range(3)]

assert TamperEvidentPlugin.verify_chain(records) is True

records[1]["message"] = "tampered"  # simulate an edited log line
assert TamperEvidentPlugin.verify_chain(records) is False
```

### Alerting on errors

`AlertingPlugin` is a base class for firing an external alert on ERROR/FATAL
(or any configurable `threshold`). It never blocks the log call that
triggered it — the actual send runs on a background thread — and repeated
identical errors within `dedupe_window_seconds` collapse into a single
follow-up alert carrying an occurrence count, instead of spamming the
destination once per record. Concrete subclasses ship for Slack, PagerDuty,
and email:

```python
from logquill import Logger, PagerDutyAlertPlugin, SlackAlertPlugin

logger = Logger(
    "app",
    plugins=[
        SlackAlertPlugin("https://hooks.slack.com/services/T000/B000/xxx"),
        PagerDutyAlertPlugin("your-events-api-v2-routing-key", threshold="FATAL"),
    ],
)

logger.error("payment webhook failed")  # posts to the Slack webhook
logger.fatal("database unreachable")  # also pages via PagerDuty (threshold=FATAL)
```

Write your own destination by subclassing `AlertingPlugin` and implementing
`send_alert(record, occurrences)`; thresholding, deduplication, and the
never-block-the-caller behavior are all handled by the base class.

## Agentic & harness tracing

`.child()` makes a namespaced logger that shares the parent's transports —
attach run-scoped plugins to it without touching the parent's pipeline.
`RunPlugin` stamps `meta.run_id` and an incrementing `meta.step`; the
`.thought()/.action()/.observation()/.decision()` convenience methods are
`.info()` with `meta.kind` pre-set, for tagging agent reasoning steps; and
`with agent_log.span(name):` stamps `meta.span_id`/`meta.duration_ms` on
exit, with every record logged inside the block automatically getting
`meta.parent_span_id` — so a full run reconstructs its exact order and
nesting by sorting on `run_id`/`step`/`span_id`/`parent_span_id`:

```python
from logquill import CollectingTransport, Logger, RunPlugin

sink = CollectingTransport()
log = Logger("app", transports=[sink])
agent_log = log.child("agent").use(RunPlugin())

agent_log.thought("deciding what to do")
with agent_log.span("call_llm"):
    agent_log.action("call the model")
    agent_log.observation("got a response")
agent_log.decision("final answer ready")

for record in sink.records:
    print(record["meta"]["step"], record["meta"].get("kind"), record["message"])
# 0 thought deciding what to do
# 1 action call the model
# 2 observation got a response
# 3 span call_llm
# 4 decision final answer ready
```

### Cross-service trace correlation

`TraceContextPlugin` stamps `meta.trace_id` — distinct from `run_id`:
`trace_id` follows one request across services, `run_id` scopes one agent
run. It reads an active OpenTelemetry span's trace id first (if
`opentelemetry-api` is importable and a span is current), then an inbound
W3C `traceparent` / AWS X-Ray / GCP trace header — handed in via
`set_traceparent()` for the current thread/asyncio task, the way request
middleware would propagate one — and generates a fresh id only if neither
is available:

```python
from logquill import Logger, TraceContextPlugin
from logquill.plugins.trace_context_plugin import reset_traceparent, set_traceparent

# e.g. set once in HTTP middleware, from the inbound request's header
token = set_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
try:
    logger = Logger("billing-service", plugins=[TraceContextPlugin()])
    record = logger.info("charged card")
finally:
    reset_traceparent(token)

assert record["meta"]["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
```

### Framework adapters

`LogQuillAdapter` is a thin base class for mapping a framework's own event
callbacks onto `.thought()/.action()/.observation()/.decision()` and
`.span()` — never a reimplementation of tracing logic per framework.
`LangChainAdapter` ships behind the optional `langchain` extra. LangGraph
nodes run as ordinary LangChain `Runnable`s, so it already captures node
execution with zero extra work — for LangGraph's own checkpoint
interrupt/resume events too, see [LangGraph](#langgraph) below:

```bash
pip install logquill[langchain]
```

```python
from logquill import Logger, RunPlugin
from logquill.adapters.langchain import LangChainAdapter

log = Logger("app")
handler = LangChainAdapter(log.child("agent").use(RunPlugin()))
llm = ChatOpenAI(callbacks=[handler])  # pass in like any other tracing handler
```

LangChain's own `run_id`/`parent_run_id` are written directly onto
`meta.span_id`/`meta.parent_span_id` — the shapes already match, so this is
field renaming, not translation. `langchain-core` is never imported unless
you import `logquill.adapters.langchain` yourself.

### LangGraph

LangGraph nodes execute as ordinary LangChain `Runnable`s, so
`LangChainAdapter` alone already covers everything that happens *inside* a
node — `on_chain_start`/`on_llm_start`/`on_tool_start`/etc. all fire exactly
as they would for a plain chain. What a plain `BaseCallbackHandler` can't
see is LangGraph's own checkpoint lifecycle: `on_interrupt`/`on_resume`,
fired when a graph pauses on an `interrupt()` call (e.g. for human review)
and later resumes from a persisted checkpoint — LangGraph dispatches those
two specifically to handlers that are instances of its own
`GraphCallbackHandler`, which a plain `BaseCallbackHandler` subclass never
receives. `LangGraphAdapter` is `LangChainAdapter` plus those two:

```bash
pip install logquill[langgraph]
```

```python
from logquill import Logger, RunPlugin
from logquill.adapters.langgraph import LangGraphAdapter

log = Logger("app")
handler = LangGraphAdapter(log.child("agent").use(RunPlugin()))
graph = builder.compile(checkpointer=checkpointer)
graph.invoke(input, config={"callbacks": [handler], "configurable": {"thread_id": "1"}})
```

`on_interrupt` becomes `.observation("graph_interrupted", ...)` carrying
`checkpoint_id`, `status`, `checkpoint_ns` (the subgraph namespace path, if
nested), and each pending `Interrupt`'s `id`/`value`; `on_resume` becomes
`.action("graph_resumed", ...)` with the same checkpoint fields. Both use
the event's own `run_id` as `parent_span_id`, matching the enclosing
graph's still-open chain span — the graph hasn't ended, just paused.
`pip install logquill[langgraph]` pulls in a compatible `langchain-core`
transitively, so installing it alone is enough; `langgraph` is never
imported unless you import `logquill.adapters.langgraph` yourself.

`CrewAIAdapter` ships behind the optional `crewai` extra, listening on
CrewAI's own event bus rather than a single callback handler:

```bash
pip install logquill[crewai]
```

```python
from logquill import Logger, RunPlugin
from logquill.adapters.crewai import CrewAIAdapter

log = Logger("app")
listener = CrewAIAdapter(log.child("agent").use(RunPlugin()))  # active as soon as it's constructed
crew = Crew(agents=[...], tasks=[...])
crew.kickoff()
```

A crew kickoff and each task within it open/close a `.span()`; agent
execution, tool usage, and LLM calls become `.action()`/`.observation()`/
`.error()` pairs carrying `duration_ms`. Same field-renaming approach as
`LangChainAdapter`: CrewAI's own event bus already threads
`event.parent_event_id` and, on every "ended" event, `event.started_event_id`
(the matching "started" event's id) through its own internal
`contextvars`-backed scope stack — those map directly onto
`meta.parent_span_id`/`meta.span_id`. `crewai` is never imported unless you
import `logquill.adapters.crewai` yourself.

`LlamaIndexAdapter` ships behind the optional `llamaindex` extra:

```bash
pip install logquill[llamaindex]
```

```python
from logquill import Logger, RunPlugin
from logquill.adapters.llamaindex import LlamaIndexAdapter

log = Logger("app")
adapter = LlamaIndexAdapter(log.child("agent").use(RunPlugin()))  # active as soon as it's constructed
index.as_query_engine().query("...")
```

LlamaIndex splits instrumentation into two cooperating pieces on its own
global dispatcher, so this adapter registers one of each rather than being a
handler itself: a span handler for LlamaIndex's own method-level calls
(`query()`, `chat()`, `retrieve()`, ...), which become `span_id`/
`duration_ms` records with `parent_span_id` set for a nested call (e.g.
`retrieve()` inside `query()`); and an event handler for named events fired
*within* those calls (LLM calls, retrieval, synthesis, embedding, agent
steps), classified generically by name suffix (`*StartEvent` ->
`.action()`, `*EndEvent` -> `.observation()`, `*ErrorEvent` -> `.error()`)
rather than enumerated one by one, so a new LlamaIndex event type needs no
adapter change to show up correctly. `llama-index-core` is never imported
unless you import `logquill.adapters.llamaindex` yourself.

`AutoGenAdapter` ships behind the optional `autogen` extra. Unlike the
other three, it's not a callback/event-bus registration — (Microsoft)
AutoGen's actual integration point is a stdlib `logging.Handler` attached
to `autogen_core.EVENT_LOGGER_NAME`, where model clients and tools log
structured event *objects* (not strings), so that's what this adapter is:

```bash
pip install logquill[autogen]
```

```python
from logquill import Logger, RunPlugin
from logquill.adapters.autogen import AutoGenAdapter

log = Logger("app")
adapter = AutoGenAdapter(log.child("agent").use(RunPlugin()))  # active immediately
```

Each event becomes a flat `.action()`/`.observation()`/`.error()` record
carrying whatever fields AutoGen put on it (`agent_id`, token counts, tool
name/arguments/result, ...). Worth knowing before relying on it: unlike the
other three adapters, AutoGen's structured events carry no call-level
`span_id`/`parent_span_id`-equivalent, so there's no tree to reconstruct —
just per-event correlation via `agent_id`. **Covers (Microsoft)
`autogen-core`/`autogen-agentchat` only — not AG2.** AG2 forked from
AutoGen and, as of its 2026 rewrite, moved onto its own event-driven
architecture that no longer shares `EVENT_LOGGER_NAME` or any of these
event classes; that's a real divergence, not just a detail, so it needs its
own adapter rather than reusing this one. `autogen-core` is never imported
unless you import `logquill.adapters.autogen` yourself.

## Async dispatch & serverless safety

By default, every log call dispatches to its transports synchronously — a
slow or down sink adds latency directly to the call that triggered it. Pass
`async_dispatch=True` to move dispatch (the transport writes, plus the
`after_log` plugin hooks that follow them) onto a background thread instead,
so `.info()`/`.error()`/... return as soon as `before_log` plugin hooks have
run, without waiting on any transport's I/O:

```python
from logquill import ConsoleTransport, HTTPTransport, Logger

logger = Logger(
    "app",
    transports=[ConsoleTransport(), HTTPTransport("https://logs.example.com/ingest")],
    async_dispatch=True,
    max_queue_size=10_000,   # bounds memory if a transport stalls
    backpressure="drop_oldest",  # or "drop_newest" / "block"
)
```

`max_queue_size` bounds how many not-yet-dispatched records can pile up in
memory if a transport stalls (a down HTTP endpoint, a full disk). Once that
bound is hit, `backpressure` decides what happens next — `"drop_oldest"`
(default) evicts the oldest queued record to make room, `"drop_newest"`
discards the record that just triggered the overflow, and `"block"` makes
the calling thread wait for space instead of dropping anything. Either drop
policy logs at most one warning per minute while actively dropping, not one
per dropped record. `Logger.child()` shares its parent's queue/background
thread rather than starting a second one.

Call `logger.close()` on ordinary process shutdown — it drains any records
still queued (up to an optional `timeout`, default 5 seconds) and then
closes every transport:

```python
logger.close(timeout=5.0)
```

For code that keeps running afterward (a request handler, a serverless
invocation), use `logger.flush()` instead — it drains the queue and flushes
each transport's own internal buffer (see `BatchingTransport`) *without*
closing anything, so the logger is still usable right after:

```python
logger.flush(timeout=2.0)          # sync callers
await logger.flush_async(timeout=2.0)  # async callers — awaits instead of blocking
```

### Serverless: flush before the container freezes

A serverless execution environment (AWS Lambda, GCP Cloud Functions, Azure
Functions) can freeze or tear down immediately after your handler returns —
a record still sitting in the async queue at that instant may never reach
its transport. `with_lambda` wraps a handler so `flush()`/`flush_async()`
happens automatically, on both a normal return and an exception, before
control goes back to the platform:

```python
from logquill import ConsoleTransport, Logger, with_lambda

logger = Logger("app", transports=[ConsoleTransport()], async_dispatch=True)


@with_lambda(logger)
def handler(event, context):
    logger.info("processing request", request_id=event["requestId"])
    return {"statusCode": 200}
```

It flushes, never closes — a warm container reuses the same `Logger`/
transports on its next invocation, and `close()` would release resources
(an open file handle, a pooled connection) that invocation needs. Works
with `async def` handlers too, and accepts a list of loggers if a handler
logs through more than one. `with_cloud_function`/`with_azure_function` are
the same decorator under a name that reads naturally at each platform's own
handler definition — the flush-before-return behavior is identical across
all three.

## Context propagation, exception capture & the stdlib bridge

`bind_context()` binds request-scoped values for a `with` block — every
`Logger` call underneath it, through any method and any number of function
calls deep, picks them up in `meta` automatically, without threading them
through every function signature by hand:

```python
from logquill import Logger, bind_context

logger = Logger("app")

def process():
    return logger.info("processing")  # no request_id passed in — picked up from context

with bind_context(request_id="req-42"):
    record = process()

assert record["meta"] == {"request_id": "req-42"}
```

It's backed by a `contextvars.ContextVar`, so concurrent asyncio tasks and
threads each see their own bound context; nested `bind_context` blocks
merge, and an explicit call-site value still wins over anything bound this
way — the same override rule `ContextPlugin` uses.

Pass `exc_info=` (an exception instance, `True` for the exception currently
being handled, or an explicit `(type, value, traceback)` tuple — the same
shapes stdlib `logging` accepts) to any `Logger` method to capture a
formatted traceback into `meta["stack"]`:

```python
from logquill import Logger

logger = Logger("app")

try:
    1 / 0
except ZeroDivisionError as exc:
    record = logger.error("payment failed", exc_info=exc, order_id=42)

assert record["meta"]["order_id"] == 42
assert "ZeroDivisionError" in record["meta"]["stack"]
```

`LogQuillHandler` bridges stdlib `logging` calls — including from
third-party libraries you don't control — into a `Logger`, so they flow
through the same transports and plugins instead of needing every call site
rewritten:

```python
import logging
from logquill import Logger, LogQuillHandler

logger = Logger("app")
logging.getLogger().addHandler(LogQuillHandler(logger))

logging.getLogger("some.library").warning("retrying", extra={"attempt": 2})
# -> flows through `logger`'s transports as a WARN record with meta: {'attempt': 2}
```

`RateLimitPlugin` caps how many records with the same `(logger, level)` (or
a custom `key_func`) pass through per rolling window — for a noisy retry
loop that would otherwise flood a transport:

```python
from logquill import Logger, RateLimitPlugin

logger = Logger("app", plugins=[RateLimitPlugin(max_records=5, per_seconds=60)])

for _ in range(100):
    logger.error("connection refused")  # only the first 5 per minute ship
```

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
