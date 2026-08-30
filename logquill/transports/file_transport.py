from __future__ import annotations

from pathlib import Path
from typing import TextIO

from logquill.formatter import Formatter
from logquill.records import LogRecord
from logquill.transports.transport import Transport


class FileTransport(Transport):
    """Appends formatted records to a file, rotating when it exceeds `max_bytes`."""

    def __init__(
        self,
        path: str | Path,
        *,
        formatter: Formatter | None = None,
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
    ) -> None:
        super().__init__(formatter)
        self.path = Path(path)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file: TextIO = self.path.open("a", encoding="utf-8")

    def write(self, formatted: str, record: LogRecord) -> None:
        self._file.write(formatted + "\n")
        self._file.flush()
        if 0 < self.max_bytes <= self._file.tell():
            self._rotate()

    def _rotate(self) -> None:
        self._file.close()
        if self.backup_count > 0:
            for index in range(self.backup_count - 1, 0, -1):
                src = self.path.with_name(f"{self.path.name}.{index}")
                dst = self.path.with_name(f"{self.path.name}.{index + 1}")
                if src.exists():
                    dst.unlink(missing_ok=True)
                    src.rename(dst)
            backup = self.path.with_name(f"{self.path.name}.1")
            backup.unlink(missing_ok=True)
            self.path.rename(backup)
        else:
            self.path.unlink(missing_ok=True)
        self._file = self.path.open("a", encoding="utf-8")

    def close(self) -> None:
        self._file.close()
