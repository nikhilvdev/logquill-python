from __future__ import annotations

import copy

from logquill.logger import Logger
from logquill.plugins.tamper_evident_plugin import TamperEvidentPlugin


def test_each_record_gets_a_hash_and_prev_hash() -> None:
    logger = Logger("app.test", plugins=[TamperEvidentPlugin()])

    record = logger.info("hello")

    assert record is not None
    assert isinstance(record["meta"]["hash"], str)
    assert record["meta"]["prev_hash"] == "0" * 64


def test_chain_links_consecutive_records() -> None:
    logger = Logger("app.test", plugins=[TamperEvidentPlugin()])

    first = logger.info("one")
    second = logger.info("two")

    assert first is not None and second is not None
    assert second["meta"]["prev_hash"] == first["meta"]["hash"]


def test_verify_chain_passes_on_an_untampered_log() -> None:
    logger = Logger("app.test", plugins=[TamperEvidentPlugin()])
    records = [logger.info(f"event {i}", n=i) for i in range(5)]

    assert TamperEvidentPlugin.verify_chain(records) is True  # type: ignore[arg-type]


def test_verify_chain_detects_an_edited_message() -> None:
    logger = Logger("app.test", plugins=[TamperEvidentPlugin()])
    records = [logger.info(f"event {i}", n=i) for i in range(5)]
    tampered = [copy.deepcopy(r) for r in records]
    tampered[2]["message"] = "edited after the fact"  # type: ignore[index]

    assert TamperEvidentPlugin.verify_chain(tampered) is False  # type: ignore[arg-type]


def test_verify_chain_detects_a_removed_record() -> None:
    logger = Logger("app.test", plugins=[TamperEvidentPlugin()])
    records = [logger.info(f"event {i}", n=i) for i in range(5)]
    tampered = records[:2] + records[3:]  # remove index 2

    assert TamperEvidentPlugin.verify_chain(tampered) is False  # type: ignore[arg-type]


def test_verify_chain_detects_reordered_records() -> None:
    logger = Logger("app.test", plugins=[TamperEvidentPlugin()])
    records = [logger.info(f"event {i}", n=i) for i in range(3)]
    reordered = [records[1], records[0], records[2]]

    assert TamperEvidentPlugin.verify_chain(reordered) is False  # type: ignore[arg-type]


def test_verify_chain_on_empty_input_is_true() -> None:
    assert TamperEvidentPlugin.verify_chain([]) is True
