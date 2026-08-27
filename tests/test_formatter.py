import json

from logquill.formatter import JSONFormatter
from logquill.logger import Logger


def test_json_formatter_round_trips_record() -> None:
    logger = Logger("app.test")
    record = logger.info("hello", user_id=42)
    assert record is not None

    formatted = JSONFormatter().format(record)
    parsed = json.loads(formatted)

    assert parsed == record
