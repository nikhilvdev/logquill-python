from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from logquill.plugins.plugin import Plugin
from logquill.records import LogRecord

#: Syntactic (not semantic) patterns — matched on shape, so both false
#: positives (a random 9-digit number) and false negatives (anything that
#: doesn't look like these shapes) are expected. Override via `patterns=`
#: for anything stricter.
DEFAULT_PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    "phone": re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
}

_MAX_DEPTH = 50


class PIIRedactPlugin(Plugin):
    """Regex-based PII redaction over `meta` **values**, not just keys.

    Complements `RedactPlugin`, which redacts by exact key match —
    `PIIRedactPlugin` scans string values (recursively through nested
    dicts/lists/tuples) for emails, SSNs, credit-card numbers, and phone
    numbers, and redacts matches wherever they appear, regardless of which
    key holds them (a `notes` field containing a stray SSN is still caught).

    Detection is pattern-based by default: fast and dependency-free, but it
    matches on syntactic shape, not meaning — a random 9-digit number can
    false-positive as an SSN, and anything that doesn't fit these shapes
    (a name, a street address) is a false negative. Pass your own
    `patterns={"custom": re.compile(...)}` to extend or replace the
    defaults.

    For fuzzier, ML-based PII detection instead, pass `use_presidio=True`
    (`pip install logquill[presidio]`) to run values through Microsoft
    Presidio's `AnalyzerEngine`/`AnonymizerEngine`. Presidio is a real
    dependency (spaCy models included) — it's opt-in and imported lazily,
    so `PIIRedactPlugin` works with zero extra dependencies as long as
    `use_presidio` stays `False`.

    Recursion into nested `meta` structures is depth- and cycle-bounded, so
    a circular reference or a pathologically deep structure can't hang or
    crash the caller — it's left unredacted past the bound rather than
    raising.
    """

    def __init__(
        self,
        *,
        patterns: Mapping[str, re.Pattern[str]] | None = None,
        replacement: str = "***",
        use_presidio: bool = False,
        presidio_entities: Sequence[str] | None = None,
        presidio_language: str = "en",
    ) -> None:
        """`patterns` overrides/extends `DEFAULT_PII_PATTERNS` entirely (not
        merged) when given. `presidio_entities`/`presidio_language` are only
        used when `use_presidio=True`; loading Presidio happens here, at
        construction time, so a missing optional dependency fails fast
        rather than on the first log call."""
        self.patterns: dict[str, re.Pattern[str]] = (
            dict(patterns) if patterns is not None else dict(DEFAULT_PII_PATTERNS)
        )
        self.replacement = replacement
        self.use_presidio = use_presidio
        self.presidio_entities = list(presidio_entities) if presidio_entities else None
        self.presidio_language = presidio_language
        self._analyzer: Any = None
        self._anonymizer: Any = None
        if use_presidio:
            self._analyzer, self._anonymizer = self._load_presidio()

    @staticmethod
    def _load_presidio() -> tuple[Any, Any]:
        try:
            # stub availability for this optional dep varies by env
            from presidio_analyzer import AnalyzerEngine  # type: ignore[import-not-found]
            from presidio_anonymizer import AnonymizerEngine  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError(
                "PIIRedactPlugin(use_presidio=True) requires the optional Presidio "
                "dependencies — install with `pip install logquill[presidio]`."
            ) from exc
        return AnalyzerEngine(), AnonymizerEngine()

    def before_log(self, record: LogRecord) -> LogRecord | None:
        """Recursively redacts PII-shaped substrings anywhere in `meta`'s
        values, regardless of which key holds them."""
        record["meta"] = self._redact_value(record["meta"], set(), 0)
        return record

    def _redact_value(self, value: Any, seen: set[int], depth: int) -> Any:
        if depth > _MAX_DEPTH:
            return value
        if isinstance(value, str):
            return self._redact_text(value)
        if isinstance(value, (dict, list, tuple)):
            obj_id = id(value)
            if obj_id in seen:
                return value  # circular reference — leave as-is rather than recurse forever
            seen = seen | {obj_id}
            if isinstance(value, dict):
                return {k: self._redact_value(v, seen, depth + 1) for k, v in value.items()}
            if isinstance(value, list):
                return [self._redact_value(v, seen, depth + 1) for v in value]
            return tuple(self._redact_value(v, seen, depth + 1) for v in value)
        return value

    def _redact_text(self, text: str) -> str:
        if self.use_presidio:
            return self._redact_with_presidio(text)
        for pattern in self.patterns.values():
            text = pattern.sub(self.replacement, text)
        return text

    def _redact_with_presidio(self, text: str) -> str:
        results = self._analyzer.analyze(
            text=text, language=self.presidio_language, entities=self.presidio_entities
        )
        anonymized = self._anonymizer.anonymize(text=text, analyzer_results=results)
        return str(anonymized.text)
