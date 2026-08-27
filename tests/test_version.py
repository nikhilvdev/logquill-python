import logquill


def test_version_is_a_string() -> None:
    assert isinstance(logquill.__version__, str)
