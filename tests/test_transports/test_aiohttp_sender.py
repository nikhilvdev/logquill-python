from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

pytest.importorskip("aiohttp")

from logquill import HTTPTransport, Logger  # noqa: E402
from logquill.transports.aiohttp_sender import AiohttpSender  # noqa: E402


class _Collector:
    def __init__(self) -> None:
        self.bodies: list[bytes] = []
        self.content_types: list[str | None] = []
        self.client_ports: list[int] = []
        self.status = 200


@pytest.fixture()
def server() -> Iterator[tuple[str, _Collector]]:
    collector = _Collector()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"  # keep-alive

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers["Content-Length"])
            collector.bodies.append(self.rfile.read(length))
            collector.content_types.append(self.headers["Content-Type"])
            collector.client_ports.append(self.client_address[1])
            self.send_response(collector.status)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:  # silence
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(
        target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}/ingest", collector
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_posts_a_batch_as_ndjson(server: tuple[str, _Collector]) -> None:
    url, collector = server
    sender = AiohttpSender(timeout=5.0)
    try:
        sender(url, ['{"a":1}', '{"a":2}'])
    finally:
        sender.close()

    assert collector.bodies == [b'{"a":1}\n{"a":2}']
    assert collector.content_types == ["application/x-ndjson"]


def test_reuses_one_connection_across_batches(server: tuple[str, _Collector]) -> None:
    url, collector = server
    sender = AiohttpSender(timeout=5.0)
    try:
        for _ in range(3):
            sender(url, ["{}"])
    finally:
        sender.close()

    assert len(collector.bodies) == 3
    assert len(set(collector.client_ports)) == 1  # one TCP connection, not three


def test_an_error_status_raises(server: tuple[str, _Collector]) -> None:
    url, collector = server
    collector.status = 500
    sender = AiohttpSender(timeout=5.0)
    try:
        with pytest.raises(Exception, match="500"):
            sender(url, ["{}"])
    finally:
        sender.close()


def test_an_unreachable_endpoint_raises_and_the_sender_recovers(
    server: tuple[str, _Collector],
) -> None:
    url, collector = server
    sender = AiohttpSender(timeout=2.0)
    try:
        with pytest.raises(Exception):  # noqa: B017 - aiohttp's ClientConnectorError
            sender("http://127.0.0.1:1/ingest", ["{}"])
        sender(url, ["{}"])
    finally:
        sender.close()

    assert len(collector.bodies) == 1


def test_close_is_idempotent_and_a_later_call_starts_a_fresh_session(
    server: tuple[str, _Collector],
) -> None:
    url, collector = server
    sender = AiohttpSender(timeout=5.0)
    sender(url, ["{}"])
    sender.close()
    sender.close()

    sender(url, ["{}"])
    sender.close()

    assert len(collector.bodies) == 2


def test_http_transport_with_the_aiohttp_backend_delivers_records(
    server: tuple[str, _Collector],
) -> None:
    url, collector = server
    logger = Logger("app", transports=[HTTPTransport(url, backend="aiohttp", batch_size=2)])

    logger.info("one")
    logger.info("two")
    logger.close()

    lines = b"\n".join(collector.bodies).splitlines()
    assert len(lines) == 2
    assert b'"message":"one"' in lines[0]
