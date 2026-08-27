from logquill.levels import Level
from logquill.logger import Logger


def test_info_produces_well_formed_record() -> None:
    logger = Logger("app.test")
    record = logger.info("hello", user_id=42)

    assert record is not None
    assert record["level"] == "INFO"
    assert record["logger"] == "app.test"
    assert record["message"] == "hello"
    assert record["meta"] == {"user_id": 42}
    assert record["timestamp"].endswith("Z")


def test_level_filtering_drops_below_threshold() -> None:
    logger = Logger("app.test", level=Level.WARN)

    assert logger.debug("noisy") is None
    assert logger.info("still noisy") is None
    assert logger.warn("audible") is not None


def test_set_level_changes_threshold() -> None:
    logger = Logger("app.test", level=Level.ERROR)
    assert logger.warn("dropped") is None

    logger.set_level("trace")
    assert logger.warn("now visible") is not None


def test_all_level_methods_produce_matching_level_name() -> None:
    logger = Logger("app.test", level=Level.TRACE)

    trace = logger.trace("x")
    debug = logger.debug("x")
    info = logger.info("x")
    warn = logger.warn("x")
    error = logger.error("x")
    fatal = logger.fatal("x")

    assert trace is not None and trace["level"] == "TRACE"
    assert debug is not None and debug["level"] == "DEBUG"
    assert info is not None and info["level"] == "INFO"
    assert warn is not None and warn["level"] == "WARN"
    assert error is not None and error["level"] == "ERROR"
    assert fatal is not None and fatal["level"] == "FATAL"
