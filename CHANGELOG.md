# Changelog

All notable changes to this project are documented in this file.

## Unreleased

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
