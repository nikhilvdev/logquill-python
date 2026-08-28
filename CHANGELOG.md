# Changelog

All notable changes to this project are documented in this file.

## Unreleased

- Phase 2 transports: `Transport` base (`format`/`write`/`close`), `ConsoleTransport`
  (colorized, ERROR/FATAL to stderr), `FileTransport` (size-based rotation), and
  `HTTPTransport` (batched, newline-delimited JSON over stdlib `urllib`, with an
  injectable `sender` for tests or alternate backends). `Logger` now accepts
  `transports=[...]` and dispatches each record to them synchronously, and gained
  `.close()` to close all attached transports. Dispatch is still synchronous —
  the non-blocking queue/async path is Phase 4. Also added `CollectingTransport`,
  an in-memory transport for tests.
- Added `CODE_OF_CONDUCT.md` (Contributor Covenant v2.1), `.github/CODEOWNERS`,
  `.github/PULL_REQUEST_TEMPLATE.md`, and `CONTRIBUTING.md` documenting the
  PR workflow (branch naming, scoping, review/CI requirements, squash-merge).
- Phase 1 core API: `Level` (TRACE/DEBUG/INFO/WARN/ERROR/FATAL, matching
  logquill-js's numeric weights), `parse_level()`, the `LogRecord` shape,
  `Logger` with `.trace()/.debug()/.info()/.warn()/.error()/.fatal()` and
  `.set_level()`, and a `Formatter` protocol with a `JSONFormatter`
  implementation. Log calls return the record dict (or `None` when filtered
  by level) — no transports or dispatch yet, that's Phase 2.
- Repo scaffold: `pyproject.toml`, package skeleton, dev tooling (ruff, mypy --strict, pytest), pre-commit hooks, and CI workflow.
- Packaging metadata: expanded classifiers (OS, Topic) and keywords, added an `Issues` project URL, and fixed the `Homepage`/`Repository`/`Changelog` URLs to point at the actual `nikhilvdev/logquill-python` GitHub repo instead of a stale placeholder org.
- Added a pepy.tech download-count badge to the README for tracking installs.
