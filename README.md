# logquill

[![CI](https://github.com/nikhilvdev/logquill-python/actions/workflows/ci.yml/badge.svg)](https://github.com/nikhilvdev/logquill-python/actions/workflows/ci.yml)
[![Publish](https://github.com/nikhilvdev/logquill-python/actions/workflows/release.yml/badge.svg)](https://github.com/nikhilvdev/logquill-python/actions/workflows/release.yml)
[![PyPI](https://img.shields.io/pypi/v/logquill.svg)](https://pypi.org/project/logquill/)
[![GitHub tag](https://img.shields.io/github/v/tag/nikhilvdev/logquill-python)](https://github.com/nikhilvdev/logquill-python/tags)
[![Downloads](https://static.pepy.tech/badge/logquill)](https://pepy.tech/project/logquill)

A structured, leveled logging framework for Python with pluggable transports
and a plugin pipeline. Sibling to [`logquill` on npm](https://www.npmjs.com/package/logquill)
(`logquill-js`) — same log record shape, same level names, one mental model
across a Python + Node stack.

Status: pre-release, under active development. The core `Logger`, level
filtering, and transports are implemented; plugins and non-blocking async
dispatch are not yet — see `CHANGELOG.md` for what's landed so far.

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
dispatch lands in a later phase):

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

See [CONTRIBUTING.md](CONTRIBUTING.md) for the PR workflow, and the
[Code of Conduct](CODE_OF_CONDUCT.md) for community standards.
