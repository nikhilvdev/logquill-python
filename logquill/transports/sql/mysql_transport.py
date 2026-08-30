from __future__ import annotations

from typing import Protocol, Sequence, cast

from logquill.formatter import Formatter
from logquill.transports.sql.base_sql_transport import BaseSQLTransport, SQLLogRow


class MySQLCursorLike(Protocol):
    def execute(self, sql: str, parameters: Sequence[object] = ()) -> object: ...


class MySQLConnectionLike(Protocol):
    def cursor(self) -> MySQLCursorLike: ...
    def commit(self) -> None: ...
    def close(self) -> None: ...


class MySQLTransport(BaseSQLTransport):
    """Batches records into one parameterized multi-row `INSERT` per flush,
    via the optional `pymysql` peer dependency (pure Python — no C toolchain
    needed, unlike `mysqlclient`). Pass `dsn`-equivalent connection kwargs
    via a pre-built `connection`, or let this transport connect itself from
    `host`/`user`/`password`/`database`."""

    def __init__(
        self,
        *,
        connection: MySQLConnectionLike | None = None,
        host: str = "localhost",
        port: int = 3306,
        user: str = "root",
        password: str = "",
        database: str = "logquill",
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
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._database = database
        self._connection: MySQLConnectionLike | None = None

    def create_table_sql(self) -> str:
        return (
            f"CREATE TABLE IF NOT EXISTS {self.table_name} ("
            "id INT AUTO_INCREMENT PRIMARY KEY, "
            "timestamp TEXT NOT NULL, "
            "level VARCHAR(16) NOT NULL, "
            "logger TEXT NOT NULL, "
            "message TEXT NOT NULL, "
            "meta JSON NOT NULL, "
            "run_id TEXT, "
            "span_id TEXT, "
            "parent_span_id TEXT, "
            "trace_id TEXT"
            ")"
        )

    def _resolved_connection(self) -> MySQLConnectionLike:
        if self._injected is not None:
            return self._injected
        if self._connection is None:
            self._connection = self._import_connection()
        return self._connection

    def _import_connection(self) -> MySQLConnectionLike:
        try:
            import pymysql  # type: ignore  # stub availability for this optional dep varies by env
        except ImportError as exc:
            raise ImportError(
                "MySQLTransport: install `pymysql` to use this transport "
                "without providing a connection — `pip install logquill[mysql]`"
            ) from exc
        return cast(
            MySQLConnectionLike,
            pymysql.connect(
                host=self._host,
                port=self._port,
                user=self._user,
                password=self._password,
                database=self._database,
            ),
        )

    def close(self) -> None:
        super().close()
        if self._injected is None and self._connection is not None:
            self._connection.close()

    def _ensure_table(self) -> None:
        connection = self._resolved_connection()
        connection.cursor().execute(self.create_table_sql())
        connection.commit()

    def _insert_rows(self, rows: Sequence[SQLLogRow]) -> None:
        connection = self._resolved_connection()
        values_sql = ", ".join(["(%s, %s, %s, %s, %s, %s, %s, %s, %s)"] * len(rows))
        sql = (
            f"INSERT INTO {self.table_name} "
            "(timestamp, level, logger, message, meta, run_id, span_id, parent_span_id, trace_id) "
            f"VALUES {values_sql}"
        )
        params: list[object] = []
        for row in rows:
            params.extend(
                [
                    row["timestamp"],
                    row["level"],
                    row["logger"],
                    row["message"],
                    row["meta"],
                    row["run_id"],
                    row["span_id"],
                    row["parent_span_id"],
                    row["trace_id"],
                ]
            )
        connection.cursor().execute(sql, params)
        connection.commit()
