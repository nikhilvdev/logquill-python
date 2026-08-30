from __future__ import annotations

import sqlite3
from typing import Iterable, Protocol, Sequence

from logquill.formatter import Formatter
from logquill.transports.sql.base_sql_transport import BaseSQLTransport, SQLLogRow


class SQLiteConnectionLike(Protocol):
    def execute(self, sql: str, parameters: Sequence[object] = ()) -> object: ...
    def executemany(self, sql: str, seq_of_parameters: Iterable[Sequence[object]]) -> object: ...
    def commit(self) -> None: ...
    def close(self) -> None: ...


class SQLiteTransport(BaseSQLTransport):
    """Zero-setup SQL sink via stdlib `sqlite3` — no server process, no
    optional dependency, works against a file path or `:memory:`. Pass
    `connection` to inject an already-open connection for tests or an
    alternate setup."""

    def __init__(
        self,
        *,
        connection: SQLiteConnectionLike | None = None,
        filename: str = ":memory:",
        formatter: Formatter | None = None,
        max_records: int = 100,
        max_bytes: int = 1_000_000,
        table_name: str = "logs",
        ensure_schema: bool = False,
    ) -> None:
        super().__init__(
            formatter=formatter,
            max_records=max_records,
            max_bytes=max_bytes,
            table_name=table_name,
            ensure_schema=ensure_schema,
        )
        self._injected = connection
        self._filename = filename
        self._connection: SQLiteConnectionLike | None = None

    def _resolved_connection(self) -> SQLiteConnectionLike:
        if self._injected is not None:
            return self._injected
        if self._connection is None:
            self._connection = sqlite3.connect(self._filename)
        return self._connection

    def close(self) -> None:
        super().close()
        if self._injected is None and self._connection is not None:
            self._connection.close()

    def _ensure_table(self) -> None:
        connection = self._resolved_connection()
        connection.execute(self.create_table_sql())
        connection.commit()

    def _insert_rows(self, rows: Sequence[SQLLogRow]) -> None:
        connection = self._resolved_connection()
        sql = (
            f"INSERT INTO {self.table_name} "
            "(timestamp, level, logger, message, meta, run_id, span_id, parent_span_id, trace_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        connection.executemany(
            sql,
            [
                (
                    row["timestamp"],
                    row["level"],
                    row["logger"],
                    row["message"],
                    row["meta"],
                    row["run_id"],
                    row["span_id"],
                    row["parent_span_id"],
                    row["trace_id"],
                )
                for row in rows
            ],
        )
        connection.commit()
