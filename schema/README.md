# LogQuill record schema

`record.schema.json` is the machine-readable definition of one log record
(JSON Schema draft 2020-12). `golden_records.json` is a set of example records
that every LogQuill implementation runs its tests against. Together they are
what keeps `logquill` (Python) and `logquill` (npm) writing the same shape.

## Using the schema

```python
import json

import jsonschema

from logquill import Logger

schema = json.load(open("schema/record.schema.json"))
record = Logger("app").info("hello", user_id=42)

jsonschema.validate(record, schema)  # raises ValidationError if it doesn't conform
```

Run it from the repository root, or point `open` at wherever you keep the file.

Field names in `meta` are snake_case (`run_id`, `span_id`, `duration_ms`) in
both languages.

## What the golden records check

`golden_records.json` has four groups. A LogQuill implementation's test suite
should load the file and assert:

| Group | Assertion |
|---|---|
| `valid` | validates against `record.schema.json`, and equals itself after a JSON round trip |
| `invalid` | does **not** validate; `why` says which rule it breaks |
| `legacy` | the record parser turns `record` into exactly `parsed` (1.x records gain `schema_version: "1.0"`; a missing `meta` becomes `{}`) |
| `rejected` | the record parser refuses it |

The Python tests are `tests/test_contract.py`. To add a rule, add a case to
the right group *and* to `record.schema.json` in one change, then update the
other implementations' copies before releasing.

## Versions

`schema_version` is `"<major>.<minor>"`. A new optional field is a minor
change; anything a reader of the previous version couldn't handle is a major
one. A reader accepts records with a newer minor version (keeping fields it
doesn't know) and refuses a newer major version.
