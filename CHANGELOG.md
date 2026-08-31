# Changelog

All notable changes to this project are documented in this file.

## Unreleased

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
