# Changelog

All notable changes to this project are documented in this file.

## Unreleased

## 0.5.0 - 2026-09-01

- `LangGraphAdapter` (`pip install logquill[langgraph]`) — corrects an
  overstatement in the 0.4.0 entry below: LangGraph nodes run as ordinary
  LangChain `Runnable`s, so `LangChainAdapter` alone already captures node
  execution, but LangGraph also has its own checkpoint lifecycle —
  `on_interrupt`/`on_resume`, fired when a graph pauses on an `interrupt()`
  call (e.g. for human review) and later resumes from a persisted
  checkpoint — that LangGraph dispatches only to handlers that are
  instances of its own `GraphCallbackHandler`; a plain `BaseCallbackHandler`
  subclass (all `LangChainAdapter` is) never receives them. `LangGraphAdapter`
  is `LangChainAdapter` plus those two, mapped to `.observation
  ("graph_interrupted", ...)`/`.action("graph_resumed", ...)` carrying
  `checkpoint_id`/`status`/`checkpoint_ns`/pending `Interrupt` payloads, with
  the event's own `run_id` as `parent_span_id`. `pip install
  logquill[langgraph]` pulls in a compatible `langchain-core` transitively;
  `langgraph` is never imported unless `logquill.adapters.langgraph` is
  imported explicitly.

## 0.4.0 - 2026-09-01

- Closed three gaps found auditing Phases 1–3 against their own written
  exit criteria (each had been marked "shipped" despite this):
  - Phase 1: config loading from file/env. `load_config(dict)`,
    `logger_from_file(path)` (JSON built in; YAML via the optional
    `pip install logquill[yaml]`), and `logger_from_env(prefix=
    "LOGQUILL_")` build a `Logger` from `{"name", "level", "transports":
    [{"type"|"class", "options"}], "plugins": [...]}`. A small built-in
    `"type"` registry covers the zero-dependency transports/plugins;
    anything else (every cloud/SQL/NoSQL/queue transport, the alerting
    plugins, framework adapters, your own subclass) goes through `"class"`
    — a fully-qualified dotted path, resolved the same way `logging.
    config.dictConfig` resolves one. `{prefix}LEVEL` in the environment
    always overrides a config file's level.
  - Phase 2: `FileTransport(encrypt_key=...)` encrypts each line with
    `cryptography.fernet.Fernet` before writing — worth doing here
    specifically because cloud transports typically already encrypt
    server-side, but a local log file on disk usually doesn't. Optional
    `pip install logquill[crypto]`, imported lazily.
  - Phase 3: `SyslogTransport` — RFC 5424 messages over UDP (default) or
    TCP, stdlib `socket` only, no dependency. Not a batching transport,
    unlike the HTTP-API cloud transports: syslog is one-datagram/one-
    message-per-call.
- Fixed a pre-existing crash the plugin-pipeline hypothesis property test
  caught during this audit, unrelated to the three gaps above: any of
  `Logger`'s message-taking methods (`.info()`, `.error()`, `.action()`,
  ...) raised `TypeError: got multiple values for argument 'message'` if
  the caller's `**meta` happened to contain a key literally named
  `"message"` (and `.child()`/`.span()` had the same issue with `"name"`)
  — exactly the kind of caller-crashing bug those hypothesis tests exist
  to catch. `message`/`name` are now positional-only on every affected
  method, so a `meta`/`fixed_meta` key with that exact name now flows
  through as ordinary meta instead of colliding.
- Phase 5, trace correlation & agentic tracing, complete:
  - `Logger.child(name, **fixed_meta)` — a namespaced logger sharing the
    parent's transports, with its own plugin pipeline and optional fixed
    context injected into every record.
  - `.thought()/.action()/.observation()/.decision()` — `.info()` with
    `meta.kind` pre-set, for tagging agent reasoning steps.
  - `Logger.span(name)`, used as `with agent_log.span("call_llm"):` —
    emits one record on exit carrying `meta.span_id`/`meta.duration_ms`;
    every record logged inside the block (through any method) is
    automatically stamped with `meta.parent_span_id`, so a full run
    reconstructs its exact nesting by sorting on `span_id`/`parent_span_id`.
    Still emits its record, at `ERROR` with `meta.error` set, if the block
    raises — the exception itself propagates unchanged.
  - `RunPlugin` — stamps `meta.run_id` (generated if not given) and an
    incrementing `meta.step`; one instance scopes one run, so concurrent
    runs never share a counter.
  - `TraceContextPlugin` — stamps `meta.trace_id` for cross-service
    correlation, distinct from `run_id`. Resolves an active OpenTelemetry
    span's trace id first (best-effort, lazy import), then a W3C
    `traceparent`/AWS X-Ray/GCP trace header propagated via the new
    `set_traceparent()`/`reset_traceparent()` (a `contextvars`-based
    per-thread/asyncio-task mechanism), and generates a fresh id only if
    neither is available.
  - `LogQuillAdapter` base class + `LangChainAdapter`
    (`pip install logquill[langchain]`) — maps LangChain's
    `BaseCallbackHandler` events onto the calls above; covers LangGraph
    for free, since it shares LangChain's callback system. LangChain's own
    `run_id`/`parent_run_id` are written directly onto
    `meta.span_id`/`meta.parent_span_id`. `langchain-core` is never
    imported unless `logquill.adapters.langchain` is imported explicitly.
- `CrewAIAdapter` (`pip install logquill[crewai]`) — a second
  `LogQuillAdapter` implementation, ahead of the phase schedule (CrewAI was
  listed as a Phase 5 follow-on, not required for that phase). Listens on
  CrewAI's own event bus (`BaseEventListener`) rather than a single
  callback handler; a crew kickoff and each task open/close a `.span()`,
  while agent execution, tool usage, and LLM calls become `.action()`/
  `.observation()`/`.error()` pairs with `duration_ms`. Correlation reads
  directly off CrewAI's own `event.parent_event_id`/`event.started_event_id`
  (populated by CrewAI's own `contextvars`-backed scope stack) rather than
  tracking anything independently — the same field-renaming approach
  `LangChainAdapter` takes with LangChain's `run_id`/`parent_run_id`.
  `crewai` is never imported unless `logquill.adapters.crewai` is imported
  explicitly.
- `LlamaIndexAdapter` (`pip install logquill[llamaindex]`) — a third
  `LogQuillAdapter` implementation. LlamaIndex's own instrumentation module
  splits into two cooperating registrations on a shared dispatcher, so this
  adapter holds one of each rather than being a handler itself: a span
  handler for LlamaIndex's own method-level calls (`query()`, `chat()`,
  `retrieve()`, ...), each becoming a `span_id`/`duration_ms` record with
  `parent_span_id` set for a nested call; and an event handler for named
  events fired *within* those calls, classified generically by class-name
  suffix (`*StartEvent` -> `.action()`, `*EndEvent` -> `.observation()`,
  `*ErrorEvent` -> `.error()`) rather than enumerated one by one, so a new
  LlamaIndex event type needs no adapter change to show up correctly.
  `llama-index-core` is never imported unless `logquill.adapters.llamaindex`
  is imported explicitly.
- `AutoGenAdapter` (`pip install logquill[autogen]`) — a fourth
  `LogQuillAdapter` implementation, rounding out every framework CLAUDE.md
  names as a Phase 5 follow-on. Architecturally different from the other
  three: (Microsoft) AutoGen's actual integration point is a stdlib
  `logging.Handler` attached to `autogen_core.EVENT_LOGGER_NAME`, where
  model clients and tools log structured event objects (not strings), so
  the adapter is a `Handler` whose `emit()` unpacks that object rather than
  a callback/event-bus registration. Each event becomes a flat
  `.action()`/`.observation()`/`.error()` record; unlike the other three
  adapters, AutoGen's structured events carry no call-level
  `span_id`/`parent_span_id`-equivalent (only `agent_id`), so there's no
  span tree to reconstruct here — documented as a real limitation, not
  glossed over. Covers `autogen-core`/`autogen-agentchat` only — **not
  AG2**, which forked from AutoGen and, as of its 2026 rewrite, moved onto
  its own event-driven architecture sharing none of this (confirmed against
  its source: zero references to `EVENT_LOGGER_NAME`); unlike LangGraph
  sharing LangChain's callback system, this is a genuine divergence and AG2
  would need its own adapter. `autogen-core` is never imported unless
  `logquill.adapters.autogen` is imported explicitly.

## 0.3.0 - 2026-08-31

- Plugin pipeline, Phase 4 complete: `SamplingPlugin` gained tail-based
  elevation — with `transports=` set, a record that would be dropped is
  buffered per `meta["trace_id"]` (configurable via `trace_key`) instead of
  discarded outright, and if any later record in that trace reaches
  `elevate_at` (default `ERROR`), the whole trace — every buffered record
  plus everything after — ships, flushed straight to `transports`. Buffering
  is bounded by `max_buffered_records` and `max_traces`, oldest trace
  evicted first. Without `transports`, behavior is unchanged from plain
  rate-based sampling.
- `Logger.use()` (and the `plugins=[...]` constructor list) now accepts a
  plain function alongside a `Plugin` instance — wrapped internally as an
  anonymous `Plugin` (`FunctionPlugin`) — so a one-off `before_log`-style
  transform doesn't require subclassing `Plugin` first.
- `PIIRedactPlugin`: regex-based PII redaction over `meta` **values**
  (emails, SSNs, credit-card numbers, phone numbers), recursing through
  nested dicts/lists/tuples and matching regardless of which key holds the
  value — complements `RedactPlugin`'s exact-key matching. Depth- and
  cycle-bounded, so a circular reference or pathologically deep structure
  can't hang or crash the caller. An opt-in `use_presidio=True` mode
  (`pip install logquill[presidio]`) routes values through Microsoft
  Presidio's analyzer/anonymizer instead, for ML-based detection; Presidio
  is imported lazily and stays a real, non-default dependency.
- `TamperEvidentPlugin`: hash-chains every record (`meta.hash` over the
  record's own content plus the previous record's `meta.hash`, stored as
  `meta.prev_hash`), so editing, removing, or reordering a line in a
  written log breaks the chain from that point on. Ships with a static
  `TamperEvidentPlugin.verify_chain(records)` to check a log after the
  fact. Opt-in — hashing every record has a real, measurable CPU cost.
- `AlertingPlugin` base class + `SlackAlertPlugin`, `PagerDutyAlertPlugin`,
  and `EmailAlertPlugin`: fires on ERROR/FATAL (or any configurable
  `threshold`), with the actual send always running on a background
  thread so a slow or unreachable destination can never block the log call
  that triggered it. Repeated identical errors (same level + logger +
  message by default, or a custom `dedupe_key`) within
  `dedupe_window_seconds` collapse into one follow-up alert carrying an
  occurrence count instead of spamming the destination once per record.
  `send_alert` failures are caught and routed to the plugin's own
  `on_error`, same as any other plugin hook. Tracking is bounded to
  `max_tracked_keys` concurrent dedupe windows — alerting degrades under
  extreme cardinality, logging itself never does. All three concrete
  plugins use only the stdlib (`urllib`, `smtplib`) — no new required
  dependency.
- Fixed a pre-existing gap surfaced by a new property-based test (see
  below): `Logger`'s per-transport dispatch had no error handling, so a
  transport that failed to format or write a given record (e.g.
  `JSONFormatter` on a `meta` value containing a circular reference) would
  propagate the exception straight to the caller. Now caught and logged via
  the same `logging.getLogger("logquill")` channel `BatchingTransport`
  already uses, per transport, so one broken transport can't crash the
  caller or stop other attached transports from receiving the record.
- Added a `hypothesis`-based property test (new `dev` dependency) that
  drives the plugin pipeline (`ContextPlugin`, `RedactPlugin`,
  `PIIRedactPlugin`, `TamperEvidentPlugin`) with adversarial `meta` —
  deeply nested structures, unusual scalar types, non-JSON-serializable
  values, and circular references — asserting the pipeline never crashes
  the caller, only ever fails closed.

- New transports: SQL (`BaseSQLTransport` + `SQLiteTransport`,
  `PostgresTransport`, `MySQLTransport`), NoSQL (`MongoDBTransport`,
  `DynamoDBTransport`, `RedisTransport`), message queues
  (`BaseQueueTransport` + `KafkaTransport`, `RabbitMQTransport`,
  `SQSTransport`, `PubSubTransport`), and cloud-native sinks
  (`CloudWatchTransport`, `CloudLoggingTransport`, `AppInsightsTransport`,
  `DatadogTransport`, `ElasticsearchTransport`, `NewRelicTransport`) —
  full parity with `logquill-js` 0.2.0. All of it sits on a new shared
  `BatchingTransport` base that bounds its buffer by both record count and
  estimated byte size, swaps the buffer out before sending so a
  synchronous re-entrant flush can't double-send, and catches a failing
  send rather than propagating it to the caller (logged via Python's
  stdlib `logging.getLogger("logquill")`) — a slow or down sink can't
  crash the process. Every optional backend driver (`psycopg2-binary`,
  `pymysql`, `pymongo`, `boto3`, `redis`, `kafka-python`, `pika`,
  `google-cloud-pubsub`, `google-cloud-logging`) is a lazy, injectable
  dependency behind a new `pyproject.toml` extra (`postgres`, `mysql`,
  `mongodb`, `redis`, `kafka`, `rabbitmq`, `pubsub`, `gcp-logging`, and a
  shared `aws` extra for CloudWatch/DynamoDB/SQS, all boto3-backed); a
  missing driver raises an actionable `ImportError` rather than a
  cryptic one, and every test injects a hand-written fake instead of
  requiring a live service. `SQLiteTransport` needs no extra at all
  (stdlib `sqlite3`).

  Two deliberate departures from `logquill-js`'s implementation, same
  outward behavior: `AppInsightsTransport` posts to Application Insights'
  public ingestion endpoint via stdlib `urllib` instead of an Azure SDK
  dependency, and `SQSTransport` dispatches its 10-message chunks
  sequentially rather than concurrently, since this project's dispatch is
  still fully synchronous end to end (true concurrency arrives once a
  non-blocking async worker exists). `SyslogTransport` isn't included
  here either, matching `logquill-js` 0.2.0, which didn't ship it; it's a
  shared follow-up for both packages, not a Python-only gap.

  Also restructured `logquill/transport.py`, `console_transport.py`,
  `file_transport.py`, and `http_transport.py` into a new
  `logquill/transports/` subpackage (with `sql/`, `nosql/`, `queue/`, and
  `cloud/` subpackages) to hold the 17 new transports — a pure move, the
  public `from logquill import ...` surface is unchanged.

- Plugin pipeline: `Plugin` base (`before_log`/`after_log`/`on_error`,
  all optional to override), `ContextPlugin` (merges fixed context into
  `meta`), `RedactPlugin` (replaces sensitive `meta` values by key, case-
  insensitive), and `SamplingPlugin` (probabilistically drops records).
  `Logger` now accepts `plugins=[...]` and gained `.use(plugin)` to register
  one and chain. A plugin hook that raises is caught, routed to that same
  plugin's `on_error`, and the pipeline continues — a broken plugin can't
  crash logging, verified by test.
- Added `.github/dependabot.yml`: weekly version updates for `pip`
  dependencies and GitHub Actions.
- Added GitHub issue templates: `.github/ISSUE_TEMPLATE/bug_report.yml`,
  `feature_request.yml`, and a `config.yml` that points security reports at
  private vulnerability reporting instead of a public issue.
- Added `.github/SECURITY.md`: supported-versions policy and instructions
  to report vulnerabilities via GitHub's private vulnerability reporting
  instead of public issues. Linked from the README.
- Transports: `Transport` base (`format`/`write`/`close`), `ConsoleTransport`
  (colorized, ERROR/FATAL to stderr), `FileTransport` (size-based rotation), and
  `HTTPTransport` (batched, newline-delimited JSON over stdlib `urllib`, with an
  injectable `sender` for tests or alternate backends). `Logger` now accepts
  `transports=[...]` and dispatches each record to them synchronously, and gained
  `.close()` to close all attached transports. Dispatch is still synchronous —
  a non-blocking queue/async path isn't implemented yet. Also added
  `CollectingTransport`, an in-memory transport for tests.
- Added `CODE_OF_CONDUCT.md` (Contributor Covenant v2.1), `.github/CODEOWNERS`,
  `.github/PULL_REQUEST_TEMPLATE.md`, and `CONTRIBUTING.md` documenting the
  PR workflow (branch naming, scoping, review/CI requirements, squash-merge).
- Core API: `Level` (TRACE/DEBUG/INFO/WARN/ERROR/FATAL, matching
  logquill-js's numeric weights), `parse_level()`, the `LogRecord` shape,
  `Logger` with `.trace()/.debug()/.info()/.warn()/.error()/.fatal()` and
  `.set_level()`, and a `Formatter` protocol with a `JSONFormatter`
  implementation. Log calls return the record dict (or `None` when filtered
  by level) — no transports or dispatch yet.
- Repo scaffold: `pyproject.toml`, package skeleton, dev tooling (ruff, mypy --strict, pytest), pre-commit hooks, and CI workflow.
- Packaging metadata: expanded classifiers (OS, Topic) and keywords, added an `Issues` project URL, and fixed the `Homepage`/`Repository`/`Changelog` URLs to point at the actual `nikhilvdev/logquill-python` GitHub repo instead of a stale placeholder org.
- Added a pepy.tech download-count badge to the README for tracking installs.
