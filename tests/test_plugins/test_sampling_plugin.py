import pytest

from logquill.logger import Logger
from logquill.plugins.sampling_plugin import SamplingPlugin


def test_rate_zero_drops_everything() -> None:
    logger = Logger("app.test", plugins=[SamplingPlugin(0.0)])

    assert logger.info("hello") is None


def test_rate_one_keeps_everything() -> None:
    logger = Logger("app.test", plugins=[SamplingPlugin(1.0)])

    assert logger.info("hello") is not None


def test_invalid_rate_raises() -> None:
    with pytest.raises(ValueError):
        SamplingPlugin(1.5)


def test_custom_rng_controls_keep_or_drop() -> None:
    keep = SamplingPlugin(0.5, rng=lambda: 0.1)
    drop = SamplingPlugin(0.5, rng=lambda: 0.9)

    logger_keep = Logger("app.test", plugins=[keep])
    logger_drop = Logger("app.test", plugins=[drop])

    assert logger_keep.info("hello") is not None
    assert logger_drop.info("hello") is None
