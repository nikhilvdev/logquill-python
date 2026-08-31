from __future__ import annotations

import re
import sys
import types
from unittest.mock import MagicMock

import pytest

from logquill.logger import Logger
from logquill.plugins.pii_redact_plugin import PIIRedactPlugin


def test_redacts_email_in_a_string_value() -> None:
    logger = Logger("app.test", plugins=[PIIRedactPlugin()])

    record = logger.info("signup", note="contact me at jane.doe@example.com please")

    assert record is not None
    assert "jane.doe@example.com" not in record["meta"]["note"]
    assert "***" in record["meta"]["note"]


def test_redacts_ssn_regardless_of_key_name() -> None:
    logger = Logger("app.test", plugins=[PIIRedactPlugin()])

    record = logger.info("free text field", notes="ssn on file: 123-45-6789")

    assert record is not None
    assert "123-45-6789" not in record["meta"]["notes"]


def test_redacts_phone_number() -> None:
    logger = Logger("app.test", plugins=[PIIRedactPlugin()])

    record = logger.info("contact", note="call me at 415-555-0199")

    assert record is not None
    assert "415-555-0199" not in record["meta"]["note"]


def test_non_string_values_are_left_untouched() -> None:
    logger = Logger("app.test", plugins=[PIIRedactPlugin()])

    record = logger.info("counts", user_id=42, active=True, ratio=0.5)

    assert record is not None
    assert record["meta"] == {"user_id": 42, "active": True, "ratio": 0.5}


def test_redacts_credit_card_number() -> None:
    logger = Logger("app.test", plugins=[PIIRedactPlugin()])

    record = logger.info("payment", note="card on file: 4242 4242 4242 4242")

    assert record is not None
    assert "4242 4242 4242 4242" not in record["meta"]["note"]


def test_redacts_recursively_through_tuples() -> None:
    logger = Logger("app.test", plugins=[PIIRedactPlugin()])

    record = logger.info("tuple meta", pair=("a@example.com", "safe"))

    assert record is not None
    assert record["meta"]["pair"][0] == "***"
    assert record["meta"]["pair"][1] == "safe"


def test_redacts_recursively_through_nested_dicts_and_lists() -> None:
    logger = Logger("app.test", plugins=[PIIRedactPlugin()])

    record = logger.info(
        "nested",
        user={"email": "a@example.com", "tags": ["contact: b@example.com"]},
    )

    assert record is not None
    assert "a@example.com" not in record["meta"]["user"]["email"]
    assert "b@example.com" not in record["meta"]["user"]["tags"][0]


def test_circular_reference_does_not_crash() -> None:
    logger = Logger("app.test", plugins=[PIIRedactPlugin()])
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic

    record = logger.info("cyclic", data=cyclic)

    assert record is not None  # must not raise / hang


def test_custom_patterns_override_defaults() -> None:
    custom = {"employee_id": re.compile(r"\bEMP-\d{4}\b")}
    logger = Logger("app.test", plugins=[PIIRedactPlugin(patterns=custom, replacement="[X]")])

    record = logger.info("badge scan", note="badge EMP-1234 scanned, ssn 123-45-6789 ignored")

    assert record is not None
    assert "EMP-1234" not in record["meta"]["note"]
    assert "123-45-6789" in record["meta"]["note"]  # default ssn pattern not active


def test_use_presidio_without_dependency_installed_raises_actionable_error() -> None:
    with pytest.raises(ImportError, match="logquill\\[presidio\\]"):
        PIIRedactPlugin(use_presidio=True)


def test_use_presidio_routes_text_through_the_analyzer_and_anonymizer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Fakes injected via sys.modules — the same pattern this repo already
    # uses for other optional-dependency drivers (e.g. the cloud/NoSQL
    # transports) — so this exercises the real Presidio code path without
    # requiring the actual (heavy) dependency to be installed.
    fake_analyzer_engine = MagicMock()
    fake_analyzer_engine.return_value.analyze.return_value = "fake-analysis"

    fake_anonymizer_engine = MagicMock()
    fake_anonymize_result = MagicMock()
    fake_anonymize_result.text = "REDACTED"
    fake_anonymizer_engine.return_value.anonymize.return_value = fake_anonymize_result

    analyzer_module = types.ModuleType("presidio_analyzer")
    analyzer_module.AnalyzerEngine = fake_analyzer_engine  # type: ignore[attr-defined]
    anonymizer_module = types.ModuleType("presidio_anonymizer")
    anonymizer_module.AnonymizerEngine = fake_anonymizer_engine  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "presidio_analyzer", analyzer_module)
    monkeypatch.setitem(sys.modules, "presidio_anonymizer", anonymizer_module)

    plugin = PIIRedactPlugin(use_presidio=True, presidio_entities=["EMAIL_ADDRESS"])
    logger = Logger("app.test", plugins=[plugin])

    record = logger.info("free text", note="jane@example.com")

    assert record is not None
    assert record["meta"]["note"] == "REDACTED"
    fake_analyzer_engine.return_value.analyze.assert_called_once_with(
        text="jane@example.com", language="en", entities=["EMAIL_ADDRESS"]
    )
    fake_anonymizer_engine.return_value.anonymize.assert_called_once_with(
        text="jane@example.com", analyzer_results="fake-analysis"
    )
