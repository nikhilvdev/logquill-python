from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

from logquill import (
    TEXT_LOG_CASTS,
    TEXT_LOG_PATTERN,
    Logger,
    TextFormatter,
    parse,
    parse_logfmt,
)

LEGACY = r"(?P<when>\S+ \S+) \[(?P<level>[A-Z]+)\] (?P<code>\d+) (?P<message>.*)"


def _write(path: Path, *lines: str) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_parse_extracts_named_groups_from_a_legacy_log_file(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "legacy.log",
        "2026-01-01 10:00:00 [INFO] 200 started",
        "garbage that matches nothing",
        "2026-01-01 10:00:05 [ERROR] 503 upstream down",
    )

    entries = list(parse(path, LEGACY, cast={"code": int}))

    assert entries == [
        {"when": "2026-01-01 10:00:00", "level": "INFO", "code": 200, "message": "started"},
        {"when": "2026-01-01 10:00:05", "level": "ERROR", "code": 503, "message": "upstream down"},
    ]


def test_parse_accepts_a_string_path_a_compiled_pattern_and_any_line_iterable(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path / "a.log", "2026-01-01 10:00:00 [INFO] 200 ok")

    from_str = list(parse(str(path), re.compile(LEGACY)))
    from_stream = list(parse(io.StringIO("2026-01-01 10:00:00 [INFO] 200 ok\n"), LEGACY))
    from_list = list(parse(["2026-01-01 10:00:00 [INFO] 200 ok\r\n"], LEGACY))

    assert from_str == from_stream == from_list
    assert from_str[0]["message"] == "ok"


def test_parse_leaves_optional_groups_that_did_not_match_as_none() -> None:
    entries = list(parse(["a b", "a"], r"(?P<first>\w)(?: (?P<second>\w))?$", cast={"second": str}))

    assert entries == [{"first": "a", "second": "b"}, {"first": "a", "second": None}]


def test_parse_is_lazy_and_streams(tmp_path: Path) -> None:
    lines = iter(["2026-01-01 10:00:00 [INFO] 1 a", "2026-01-01 10:00:00 [INFO] 2 b"])
    consumed = 0

    def source() -> object:
        nonlocal consumed
        for line in lines:
            consumed += 1
            yield line

    iterator = parse(source(), LEGACY)  # type: ignore[arg-type]
    assert consumed == 0
    next(iterator)
    assert consumed == 1


def test_parse_rejects_a_pattern_without_named_groups() -> None:
    with pytest.raises(ValueError, match="no named groups"):
        parse(["x"], r"\d+")


def test_parse_rejects_a_cast_for_an_unknown_group() -> None:
    with pytest.raises(ValueError, match="not named groups"):
        parse(["x"], r"(?P<a>x)", cast={"b": int})


def test_parse_reports_the_line_number_when_a_cast_fails() -> None:
    lines = ["2026-01-01 10:00:00 [INFO] 200 fine", "2026-01-01 10:00:00 [INFO] 99999999 fine"]

    def strict(value: str) -> int:
        if len(value) > 3:
            raise ValueError("too long")
        return int(value)

    with pytest.raises(ValueError, match=r"line 2: cast for 'code' failed"):
        list(parse(lines, LEGACY, cast={"code": strict}))


def test_parse_reads_back_what_text_formatter_wrote() -> None:
    logger = Logger("app.api")
    record = logger.info("user signed up", user_id=42, note="two words")
    assert record is not None
    line = TextFormatter().format(record)

    (entry,) = parse([line], TEXT_LOG_PATTERN, cast=TEXT_LOG_CASTS)

    assert entry["level"] == "INFO"
    assert entry["logger"] == "app.api"
    assert entry["message"] == "user signed up"
    assert entry["meta"] == {"user_id": 42, "note": "two words"}


def test_parse_logfmt_handles_bare_keys_duplicates_and_escapes() -> None:
    fields = parse_logfmt(r'flag a=1 a=2 msg="say \"hi\"\n" u="é" plain=x=y')

    assert fields["flag"] == ""
    assert fields["a"] == "2"
    assert fields["msg"] == 'say "hi"\n'
    assert fields["u"] == "é"
    assert fields["plain"] == "x=y"
