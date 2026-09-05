from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from logquill.plugins.plugin import Plugin
from logquill.records import LogRecord

GENESIS_HASH = "0" * 64


class TamperEvidentPlugin(Plugin):
    """Hash-chains every record so tampering with a written log can be
    detected after the fact.

    Each record gets `meta.hash` = a SHA-256 hex digest over the record's
    own content plus the previous record's hash (`meta.prev_hash`) — the
    same hash-chain construction used by tamper-evident/append-only logs:
    editing or deleting any one line breaks every hash after it in the
    chain, even if the tamperer edits the file directly and not through
    this plugin. Opt-in — hashing every record has a real, measurable CPU
    cost, so it isn't part of the default pipeline.

    Verify a previously-written log with `TamperEvidentPlugin.verify_chain`,
    which re-derives each record's hash from its content and confirms it
    matches both the stored `meta.hash` and the chain built from the
    records before it, in order.
    """

    def __init__(self, *, genesis_hash: str = GENESIS_HASH) -> None:
        """`genesis_hash` is the `prev_hash` used for the very first record
        in the chain; override it to start a new chain that continues from
        a previously-recorded hash (e.g. across a log rotation)."""
        self._genesis_hash = genesis_hash
        self._last_hash = genesis_hash

    def before_log(self, record: LogRecord) -> LogRecord | None:
        """Stamps `meta.prev_hash`/`meta.hash`, chaining this record onto
        the previous one this plugin instance processed."""
        prev_hash = self._last_hash
        digest = _compute_hash(record, prev_hash)
        record["meta"] = {**record["meta"], "prev_hash": prev_hash, "hash": digest}
        self._last_hash = digest
        return record

    @staticmethod
    def verify_chain(
        records: Iterable[Mapping[str, Any]], *, genesis_hash: str = GENESIS_HASH
    ) -> bool:
        """Return `True` iff every record's hash matches its content plus the
        previous record's hash, in the given order. Returns `False` at the
        first break in the chain (an edited, removed, or reordered record).
        """
        prev_hash = genesis_hash
        for record in records:
            meta = record.get("meta", {})
            stored_hash = meta.get("hash")
            stored_prev_hash = meta.get("prev_hash")
            if stored_hash is None or stored_prev_hash != prev_hash:
                return False
            if _compute_hash(record, prev_hash) != stored_hash:
                return False
            prev_hash = stored_hash
        return True


def _compute_hash(record: Mapping[str, Any], prev_hash: str) -> str:
    meta = record.get("meta", {})
    payload = json.dumps(
        {
            "timestamp": record.get("timestamp"),
            "level": record.get("level"),
            "logger": record.get("logger"),
            "message": record.get("message"),
            "meta": {k: v for k, v in meta.items() if k not in ("hash", "prev_hash")},
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(f"{prev_hash}{payload}".encode()).hexdigest()
