# Migrating from logquill 1.x to 2.0

2.0 raises the minimum Python version and extends the record shape shared with
`logquill` on npm. Application code that only calls `logger.info(...)` and
friends needs no changes; what changes is what's on disk and on the wire, and
which Python you run.

## 1. Python 3.10 or newer

`logquill` 2.0 requires Python 3.10+ (it was 3.8+). It is tested on 3.10
through 3.14. On an older interpreter, pip keeps installing the 1.x line.

## 2. Every record carries `schema_version`

Records now start with `"schema_version": "2.0"`:

```json
{"schema_version":"2.0","timestamp":"2026-01-01T00:00:00.000Z","level":"INFO","logger":"app","message":"hello","meta":{}}
```

**If you read logs** — a parser, a dashboard, a SIEM rule — make sure it
tolerates one extra top-level key. Nothing was renamed or removed; a strict
"exactly these five keys" check is the only thing that breaks.

**If you have existing 1.x logs**, they don't need converting. A record with no
`schema_version` is a 1.x record, and `parse_record` reads both:

```python
import json

from logquill import parse_record

line = '{"timestamp":"2026-01-01T00:00:00.000Z","level":"INFO","logger":"app","message":"hi"}'

record = parse_record(json.loads(line))  # a 1.x or 2.x line
assert record["schema_version"] == "1.0"  # "2.0" for a 2.x record
assert record["meta"] == {}
```

It fills in `"1.0"` and an empty `meta` if either is missing, keeps every other
key, and raises `ValueError` — saying what to fix — for a record that isn't a
LogQuill record, or one written by a newer major version.

**Hash-chained logs** (`TamperEvidentPlugin`) keep verifying: a chain written by
1.x verifies unchanged, and 2.x chains additionally cover `schema_version` and
`llm`, so editing either is caught.

## 3. New optional fields

These are defined so both languages agree on them. `logger.llm_call()` writes
the `llm` block, `span(capture_state=...)` writes `state_diff`, and repeated tool
calls get `retry_count` automatically; nothing else writes them, and no record
has them unless you use those.

| Field | Where | Type |
|---|---|---|
| `llm.model`, `llm.finish_reason` | top level, `llm` block | string |
| `llm.tokens_in`, `llm.tokens_out` | `llm` block | integer ≥ 0 |
| `llm.cost_usd`, `llm.latency_ms` | `llm` block | number ≥ 0 |
| `meta.retry_count` | `meta` | integer ≥ 0 |
| `meta.state_diff` | `meta` | object |
| `meta.mcp.server`, `meta.mcp.tool` | `meta` | string |
| `meta.tool`, `meta.tool_call_id`, `meta.provider`, `meta.agent_name`, `meta.agent_id`, `meta.response_model` | `meta` | string |
| `meta.operation` | `meta` | `chat`, `text_completion` or `invoke_agent` |
| `meta.input_messages`, `meta.output_messages` | `meta` | array (opt-in prompt/completion content) |

`llm` is its own block, not part of `meta`, because cost and latency
dashboards need stable names for it. A record that isn't an LLM call has no
`llm` key.

## 4. The published schema

`schema/record.schema.json` (JSON Schema 2020-12) defines a record precisely.
The top level is closed — `schema_version`, `timestamp`, `level`, `logger`,
`message`, `meta` and `llm` only — so put your own fields in `meta`, which stays
free-form. `schema/golden_records.json` holds example records that this package
and `logquill` on npm both test against.

## 5. Small things

- `LogRecord` gained `schema_version` (required) and `llm` (optional), and
  `create_record()` sets them. If you build `LogRecord` values by hand in your
  own transport or plugin, add `schema_version=SCHEMA_VERSION`, or build them
  from `create_record()`.
- If a transport of yours rebuilds a record from its five 1.x fields, copy the
  record instead (`{**record, "meta": new_meta}`) so `schema_version` and `llm`
  aren't dropped.
