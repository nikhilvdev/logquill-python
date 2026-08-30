from typing import List, Sequence, Tuple

from logquill.logger import Logger
from logquill.transports.http_transport import HTTPTransport


class FakeSender:
    """Fake sink standing in for the network call, so tests never hit the wire."""

    def __init__(self) -> None:
        self.calls: List[Tuple[str, Sequence[str]]] = []

    def __call__(self, url: str, batch: Sequence[str]) -> None:
        self.calls.append((url, list(batch)))


def test_batches_until_batch_size_is_reached() -> None:
    sender = FakeSender()
    transport = HTTPTransport("https://example.com/logs", batch_size=2, sender=sender)
    logger = Logger("app.test", transports=[transport])

    logger.info("one")
    assert sender.calls == []

    logger.info("two")
    assert len(sender.calls) == 1
    assert len(sender.calls[0][1]) == 2


def test_close_flushes_a_partial_batch() -> None:
    sender = FakeSender()
    transport = HTTPTransport("https://example.com/logs", batch_size=10, sender=sender)
    logger = Logger("app.test", transports=[transport])

    logger.info("only one")
    logger.close()

    assert len(sender.calls) == 1
    assert len(sender.calls[0][1]) == 1


def test_close_on_empty_batch_sends_nothing() -> None:
    sender = FakeSender()
    transport = HTTPTransport("https://example.com/logs", sender=sender)

    transport.close()

    assert sender.calls == []
