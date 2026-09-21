from __future__ import annotations

import io
import tempfile
from pathlib import Path
from typing import Any, Sequence

from adversarial import meta_dicts
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from logquill import (
    BatchingTransport,
    ConsoleTransport,
    FileTransport,
    HTTPTransport,
    LogfmtFormatter,
    Logger,
    LogRecord,
    TextFormatter,
)

_settings = settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])


@_settings
@given(meta=meta_dicts)
def test_console_transport_never_crashes_the_caller(meta: dict[str, Any]) -> None:
    for formatter in (None, TextFormatter(), LogfmtFormatter()):
        out, err = io.StringIO(), io.StringIO()
        transport = ConsoleTransport(formatter=formatter, stdout=out, stderr=err)
        logger = Logger("app", transports=[transport])

        logger.info("adversarial", **meta)
        logger.error("adversarial", **meta)


@_settings
@given(meta=meta_dicts)
def test_file_transport_never_crashes_the_caller_and_keeps_one_record_per_line(
    meta: dict[str, Any],
) -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "app.log"
        transport = FileTransport(path)
        logger = Logger("app", transports=[transport])

        logger.info("adversarial", **meta)
        logger.info("after")
        transport.close()

        lines = path.read_text(encoding="utf-8").splitlines()
        assert lines[-1].endswith('"message":"after","meta":{}}')


@_settings
@given(meta=meta_dicts)
def test_file_transport_with_a_text_formatter_survives_hostile_meta(
    meta: dict[str, Any],
) -> None:
    with tempfile.TemporaryDirectory() as directory:
        transport = FileTransport(Path(directory) / "app.log", formatter=LogfmtFormatter())
        logger = Logger("app", transports=[transport])

        logger.info("adversarial", **meta)
        logger.info("after")
        transport.close()


@_settings
@given(metas=st.lists(meta_dicts, max_size=30))
def test_http_transport_buffer_stays_bounded_and_every_record_is_delivered_once(
    metas: list[dict[str, Any]],
) -> None:
    sent: list[str] = []

    def sender(url: str, batch: Sequence[str]) -> None:
        sent.extend(batch)

    transport = HTTPTransport("http://unused", batch_size=5, max_bytes=2_000, sender=sender)
    logger = Logger("app", transports=[transport])

    for meta in metas:
        logger.info("adversarial", **meta)
        assert len(transport._batch) < 5
        assert transport._batch_bytes < 2_000

    transport.close()
    assert len(sent) == len(metas)


class _Recording(BatchingTransport[LogRecord]):
    def __init__(self, *, max_records: int, max_bytes: int) -> None:
        super().__init__(max_records=max_records, max_bytes=max_bytes)
        self.delivered = 0

    def _send_batch(self, batch: Sequence[LogRecord]) -> None:
        self.delivered += len(batch)


@_settings
@given(metas=st.lists(meta_dicts, max_size=30))
def test_batching_transport_buffer_stays_bounded_by_count_and_bytes(
    metas: list[dict[str, Any]],
) -> None:
    transport = _Recording(max_records=4, max_bytes=1_500)
    logger = Logger("app", transports=[transport])

    for meta in metas:
        logger.info("adversarial", **meta)
        assert len(transport._buffer) < 4
        assert transport._buffer_bytes < 1_500

    transport.close()
    assert transport.delivered == len(metas)
