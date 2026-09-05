"""The `logquill` command-line entry point (`pip install logquill` → `logquill tail ...`)."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
from pathlib import Path
from typing import IO, Any, Sequence

from logquill.levels import Level, parse_level

_COLORS = {
    Level.TRACE: "\x1b[90m",
    Level.DEBUG: "\x1b[36m",
    Level.INFO: "\x1b[32m",
    Level.WARN: "\x1b[33m",
    Level.ERROR: "\x1b[31m",
    Level.FATAL: "\x1b[35m",
}
_RESET = "\x1b[0m"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="logquill", description="LogQuill command-line tools for local development."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    tail_parser = subparsers.add_parser(
        "tail", help="Print (and optionally follow) a LogQuill JSONL log file."
    )
    tail_parser.add_argument("file", help="Path to a LogQuill JSONL log file.")
    tail_parser.add_argument(
        "--level",
        default=None,
        help="Only show records at or above this level (e.g. --level=error).",
    )
    tail_parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON lines instead of human-readable text.",
    )
    tail_parser.add_argument(
        "-f",
        "--follow",
        action="store_true",
        help="Keep watching the file and print new records as they're appended.",
    )
    tail_parser.add_argument(
        "-n",
        "--lines",
        type=int,
        default=None,
        metavar="N",
        help="Only show the last N matching records instead of the whole file.",
    )
    tail_parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colorization, even when writing to a terminal.",
    )
    return parser


def _passes_filter(record: dict[str, Any], min_level: Level | None) -> bool:
    if min_level is None:
        return True
    try:
        return parse_level(record.get("level")) >= min_level  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def _parse_line(line: str, *, warn_stream: IO[str]) -> dict[str, Any] | None:
    line = line.strip()
    if not line:
        return None
    try:
        parsed = json.loads(line)
    except json.JSONDecodeError:
        warn_stream.write(f"logquill tail: skipping malformed JSON line: {line[:200]!r}\n")
        return None
    if not isinstance(parsed, dict):
        warn_stream.write(f"logquill tail: skipping non-object JSON line: {line[:200]!r}\n")
        return None
    return parsed


def _format_human(record: dict[str, Any], *, colorize: bool) -> str:
    level_name = str(record.get("level", "?"))
    timestamp = record.get("timestamp", "?")
    logger_name = record.get("logger", "?")
    message = record.get("message", "")
    meta = record.get("meta") or {}

    line = f"{timestamp} {level_name:<5} {logger_name}: {message}"
    if meta:
        line += f" {json.dumps(meta, separators=(',', ':'), default=str)}"

    if colorize:
        try:
            color = _COLORS.get(parse_level(level_name))
        except (TypeError, ValueError):
            color = None
        if color:
            line = f"{color}{line}{_RESET}"
    return line


def _emit(record: dict[str, Any], *, as_json: bool, colorize: bool, out: IO[str]) -> None:
    if as_json:
        out.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")
    else:
        out.write(_format_human(record, colorize=colorize) + "\n")
    out.flush()


def _read_existing(
    path: Path,
    *,
    min_level: Level | None,
    lines: int | None,
    as_json: bool,
    colorize: bool,
    out: IO[str],
    warn_stream: IO[str],
) -> int:
    """Prints every matching record currently in the file; returns the byte offset at EOF."""
    matched: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            record = _parse_line(raw_line, warn_stream=warn_stream)
            if record is not None and _passes_filter(record, min_level):
                matched.append(record)
        offset = f.tell()

    if lines is not None:
        matched = matched[-lines:]
    for record in matched:
        _emit(record, as_json=as_json, colorize=colorize, out=out)
    return offset


def _follow(
    path: Path,
    offset: int,
    *,
    min_level: Level | None,
    as_json: bool,
    colorize: bool,
    out: IO[str],
    warn_stream: IO[str],
    poll_interval: float = 0.5,
    max_iterations: int | None = None,
) -> None:
    """Polls `path` for lines appended after `offset`, forever unless `max_iterations` is set.

    A polling loop rather than an inotify/kqueue watch: it keeps this module
    dependency-free and behaves the same across platforms, at the cost of up to
    `poll_interval` seconds of latency on a new line — an acceptable trade for a
    local dev tool.
    """
    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        iterations += 1
        try:
            with path.open("r", encoding="utf-8") as f:
                f.seek(offset)
                new_lines = f.readlines()
                offset = f.tell()
        except FileNotFoundError:
            time.sleep(poll_interval)
            continue

        for raw_line in new_lines:
            record = _parse_line(raw_line, warn_stream=warn_stream)
            if record is not None and _passes_filter(record, min_level):
                _emit(record, as_json=as_json, colorize=colorize, out=out)

        time.sleep(poll_interval)


def _run_tail(
    args: argparse.Namespace,
    *,
    min_level: Level | None,
    out: IO[str],
    warn_stream: IO[str],
) -> int:
    path = Path(args.file)
    if not path.exists():
        warn_stream.write(f"logquill tail: no such file: {args.file}\n")
        return 1

    colorize = not args.no_color and not args.json and getattr(out, "isatty", lambda: False)()
    offset = _read_existing(
        path,
        min_level=min_level,
        lines=args.lines,
        as_json=args.json,
        colorize=colorize,
        out=out,
        warn_stream=warn_stream,
    )

    if args.follow:
        with contextlib.suppress(KeyboardInterrupt):
            _follow(
                path,
                offset,
                min_level=min_level,
                as_json=args.json,
                colorize=colorize,
                out=out,
                warn_stream=warn_stream,
            )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "tail":
        parser.error(f"Unknown command: {args.command}")

    try:
        min_level = parse_level(args.level) if args.level is not None else None
    except ValueError as exc:
        parser.error(str(exc))
        return 2  # pragma: no cover - argparse.error() already exits

    return _run_tail(args, min_level=min_level, out=sys.stdout, warn_stream=sys.stderr)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
