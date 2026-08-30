from pathlib import Path

from logquill.levels import Level
from logquill.logger import Logger
from logquill.records import create_record
from logquill.transports.file_transport import FileTransport


def test_writes_are_appended_to_the_file(tmp_path: Path) -> None:
    log_path = tmp_path / "app.log"
    transport = FileTransport(log_path)
    logger = Logger("app.test", transports=[transport])

    logger.info("first")
    logger.info("second")
    transport.close()

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert "first" in lines[0]
    assert "second" in lines[1]


def test_rotation_moves_current_file_to_backup(tmp_path: Path) -> None:
    log_path = tmp_path / "app.log"
    transport = FileTransport(log_path, max_bytes=1, backup_count=2)
    logger = Logger("app.test", transports=[transport])

    logger.info("first")
    logger.info("second")
    transport.close()

    assert (tmp_path / "app.log.1").exists()
    assert log_path.exists()


def test_creates_parent_directories(tmp_path: Path) -> None:
    log_path = tmp_path / "nested" / "dir" / "app.log"
    transport = FileTransport(log_path)
    record = create_record(level=Level.INFO, logger="app.test", message="hi", meta={})

    transport.write(transport.format(record), record)
    transport.close()

    assert log_path.exists()
