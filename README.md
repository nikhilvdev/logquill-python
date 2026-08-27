# logquill

A structured, leveled logging framework for Python with pluggable transports
and a plugin pipeline. Sibling to [`logquill` on npm](https://www.npmjs.com/package/logquill)
(`logquill-js`) — same log record shape, same level names, one mental model
across a Python + Node stack.

Status: pre-release, under active development.

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
