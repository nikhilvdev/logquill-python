# logquill

[![CI](https://github.com/nikhilvdev/logquill-python/actions/workflows/ci.yml/badge.svg)](https://github.com/nikhilvdev/logquill-python/actions/workflows/ci.yml)
[![Publish](https://github.com/nikhilvdev/logquill-python/actions/workflows/release.yml/badge.svg)](https://github.com/nikhilvdev/logquill-python/actions/workflows/release.yml)
[![PyPI](https://img.shields.io/pypi/v/logquill.svg)](https://pypi.org/project/logquill/)
[![GitHub tag](https://img.shields.io/github/v/tag/nikhilvdev/logquill-python)](https://github.com/nikhilvdev/logquill-python/tags)

A structured, leveled logging framework for Python with pluggable transports
and a plugin pipeline. Sibling to [`logquill` on npm](https://www.npmjs.com/package/logquill)
(`logquill-js`) — same log record shape, same level names, one mental model
across a Python + Node stack.

Status: pre-release, under active development. The core logging API
(`Logger`, transports, formatters, plugins) is not implemented yet — see
`CHANGELOG.md` for what's landed so far.

## Install

```bash
pip install logquill
```

```python
import logquill

print(logquill.__version__)
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
