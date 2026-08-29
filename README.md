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
- **Pluggable transports** — `ConsoleTransport` (colorized, stderr for errors), `FileTransport` (rotation), `HTTPTransport` (batched); write your own by subclassing `Transport`
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
