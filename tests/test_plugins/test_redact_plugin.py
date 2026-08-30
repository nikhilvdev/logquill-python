from logquill.logger import Logger
from logquill.plugins.redact_plugin import RedactPlugin


def test_redacts_default_sensitive_keys() -> None:
    logger = Logger("app.test", plugins=[RedactPlugin()])

    record = logger.info("login", password="hunter2", user_id=42)

    assert record is not None
    assert record["meta"]["password"] == "***"
    assert record["meta"]["user_id"] == 42


def test_matches_keys_case_insensitively() -> None:
    logger = Logger("app.test", plugins=[RedactPlugin()])

    record = logger.info("login", Password="hunter2")

    assert record is not None
    assert record["meta"]["Password"] == "***"


def test_custom_keys_and_replacement() -> None:
    logger = Logger("app.test", plugins=[RedactPlugin(keys=["ssn"], replacement="[REDACTED]")])

    record = logger.info("submit", ssn="123-45-6789", password="not redacted here")

    assert record is not None
    assert record["meta"]["ssn"] == "[REDACTED]"
    assert record["meta"]["password"] == "not redacted here"
