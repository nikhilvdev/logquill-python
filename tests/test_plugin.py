from __future__ import annotations

from logquill.logger import Logger
from logquill.plugin import Plugin
from logquill.records import LogRecord
from logquill.transport import CollectingTransport


class UppercasePlugin(Plugin):
    def before_log(self, record: LogRecord) -> LogRecord | None:
        record["message"] = record["message"].upper()
        return record


class DroppingPlugin(Plugin):
    def before_log(self, record: LogRecord) -> LogRecord | None:
        return None


class SpyPlugin(Plugin):
    def __init__(self) -> None:
        self.errors: list[tuple[Exception, LogRecord]] = []
        self.after_log_calls: list[LogRecord] = []

    def after_log(self, record: LogRecord) -> None:
        self.after_log_calls.append(record)

    def on_error(self, exc: Exception, record: LogRecord) -> None:
        self.errors.append((exc, record))


class BrokenBeforeLogPlugin(SpyPlugin):
    def before_log(self, record: LogRecord) -> LogRecord | None:
        raise RuntimeError("boom")


class BrokenAfterLogPlugin(SpyPlugin):
    def after_log(self, record: LogRecord) -> None:
        super().after_log(record)
        raise RuntimeError("boom")


def test_before_log_can_transform_the_record() -> None:
    sink = CollectingTransport()
    logger = Logger("app.test", transports=[sink], plugins=[UppercasePlugin()])

    record = logger.info("hello")

    assert record is not None
    assert record["message"] == "HELLO"
    assert sink.records == [record]


def test_before_log_returning_none_drops_the_record() -> None:
    sink = CollectingTransport()
    logger = Logger("app.test", transports=[sink], plugins=[DroppingPlugin()])

    assert logger.info("hello") is None
    assert sink.records == []


def test_broken_before_log_does_not_crash_logging() -> None:
    sink = CollectingTransport()
    broken = BrokenBeforeLogPlugin()
    logger = Logger("app.test", transports=[sink], plugins=[broken])

    record = logger.info("hello")

    assert record is not None
    assert sink.records == [record]
    assert len(broken.errors) == 1
    assert isinstance(broken.errors[0][0], RuntimeError)


def test_broken_before_log_does_not_stop_remaining_plugins_from_running() -> None:
    sink = CollectingTransport()
    plugins = [BrokenBeforeLogPlugin(), UppercasePlugin()]
    logger = Logger("app.test", transports=[sink], plugins=plugins)

    record = logger.info("hello")

    assert record is not None
    assert record["message"] == "HELLO"


def test_broken_after_log_does_not_crash_logging_or_skip_remaining_plugins() -> None:
    broken = BrokenAfterLogPlugin()
    spy = SpyPlugin()
    logger = Logger("app.test", plugins=[broken, spy])

    record = logger.info("hello")

    assert record is not None
    assert broken.after_log_calls == [record]
    assert len(broken.errors) == 1
    assert spy.after_log_calls == [record]


def test_use_registers_a_plugin_and_returns_self_for_chaining() -> None:
    sink = CollectingTransport()
    logger = Logger("app.test", transports=[sink])

    result = logger.use(UppercasePlugin())

    assert result is logger
    logger.info("hi")
    assert sink.records[0]["message"] == "HI"
