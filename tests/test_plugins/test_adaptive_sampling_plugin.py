from __future__ import annotations

import pytest

from logquill import Logger
from logquill.plugins.adaptive_sampling_plugin import AdaptiveSamplingPlugin
from logquill.transports.transport import CollectingTransport


def _logger(**kwargs: object) -> tuple[Logger, CollectingTransport, AdaptiveSamplingPlugin]:
    sink = CollectingTransport()
    plugin = AdaptiveSamplingPlugin(**kwargs)  # type: ignore[arg-type]
    return Logger("app.test", transports=[sink], plugins=[plugin]), sink, plugin


# --- construction validation --------------------------------------------------


@pytest.mark.parametrize("field", ["base_rate", "min_rate", "max_rate"])
def test_a_rate_outside_0_1_raises(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        AdaptiveSamplingPlugin(**{field: 1.5})  # type: ignore[arg-type]


def test_min_rate_above_max_rate_raises() -> None:
    with pytest.raises(ValueError, match="min_rate"):
        AdaptiveSamplingPlugin(min_rate=0.9, max_rate=0.1)


# --- always-kept categories ---------------------------------------------------


def test_errors_are_always_kept_regardless_of_sampling() -> None:
    logger, sink, _ = _logger(base_rate=0.0, rng=lambda: 0.99)

    logger.error("always kept")

    assert len(sink.records) == 1


def test_fatal_is_also_always_kept() -> None:
    logger, sink, _ = _logger(base_rate=0.0, rng=lambda: 0.99)

    logger.fatal("always kept")

    assert len(sink.records) == 1


def test_ordinary_info_is_dropped_when_the_rate_misses() -> None:
    logger, sink, _ = _logger(base_rate=0.0, rng=lambda: 0.99)

    logger.info("dropped")

    assert sink.records == []


def test_a_slow_span_is_always_kept() -> None:
    logger, sink, _ = _logger(base_rate=0.0, rng=lambda: 0.99, slow_ms=10)

    # an explicit duration_ms in **meta overrides the span's own computed
    # timing (SpanContext.__exit__ unpacks it last), making this deterministic
    with logger.span("work", duration_ms=50):
        pass

    assert [r["message"] for r in sink.records] == ["work"]


def test_a_fast_span_is_not_automatically_kept() -> None:
    sink = CollectingTransport()
    plugin = AdaptiveSamplingPlugin(base_rate=0.0, rng=lambda: 0.99, slow_ms=10_000)
    logger = Logger("app.test", transports=[sink], plugins=[plugin])

    with logger.span("fast"):
        pass

    assert sink.records == []


def test_a_non_span_record_is_never_treated_as_slow_even_with_a_duration_ms() -> None:
    logger, sink, _ = _logger(base_rate=0.0, rng=lambda: 0.99, slow_ms=10)

    logger.info("not a span", duration_ms=9999)

    assert sink.records == []


def test_keep_at_is_configurable() -> None:
    logger, sink, _ = _logger(base_rate=0.0, rng=lambda: 0.99, keep_at="WARN")

    logger.warn("kept at the lower threshold")
    logger.info("still dropped")

    assert [r["message"] for r in sink.records] == ["kept at the lower threshold"]


# --- byte budget ---------------------------------------------------------------


def test_the_byte_budget_caps_records_within_one_window() -> None:
    logger, sink, _ = _logger(
        base_rate=1.0, rng=lambda: 0.0, max_bytes_per_second=300, clock=lambda: 0.0
    )

    for i in range(20):
        logger.info("x" * 50, i=i)

    assert 0 < len(sink.records) < 20


def test_a_record_too_big_for_an_empty_budget_is_dropped() -> None:
    logger, sink, _ = _logger(
        base_rate=1.0, rng=lambda: 0.0, max_bytes_per_second=5, clock=lambda: 0.0
    )

    logger.info("way more than five bytes of content here")

    assert sink.records == []


def test_the_byte_budget_resets_on_a_new_window() -> None:
    clock = {"t": 0.0}
    logger, sink, _ = _logger(
        base_rate=1.0, rng=lambda: 0.0, max_bytes_per_second=200, clock=lambda: clock["t"]
    )

    logger.info("x" * 40)  # ~161 bytes: fits the 200-byte budget
    logger.info("y" * 40)  # a second one this window would not: dropped
    assert len(sink.records) == 1

    clock["t"] = 10.0  # well past window_seconds=1.0: budget resets
    logger.info("z" * 40)

    assert len(sink.records) == 2


# --- adaptivity ------------------------------------------------------------


def test_rate_rises_after_a_window_with_low_demand() -> None:
    clock = {"t": 0.0}
    logger, _, plugin = _logger(
        base_rate=0.1,
        rng=lambda: 0.0,
        clock=lambda: clock["t"],
        max_bytes_per_second=1_000_000,
    )

    logger.info("a")
    clock["t"] = 2.0
    logger.info("b")  # rolls the window; last window's demand was tiny

    assert plugin.rate > 0.1


def test_rate_falls_after_a_window_with_high_demand() -> None:
    clock = {"t": 0.0}
    logger, _, plugin = _logger(
        base_rate=0.5, rng=lambda: 0.0, clock=lambda: clock["t"], max_bytes_per_second=10
    )

    logger.info("x" * 200)  # demands far more than the 10-byte budget
    clock["t"] = 2.0
    logger.info("y")

    assert plugin.rate < 0.5


def test_rate_never_exceeds_max_rate() -> None:
    clock = {"t": 0.0}
    logger, _, plugin = _logger(
        base_rate=0.9,
        max_rate=0.95,
        rng=lambda: 0.0,
        clock=lambda: clock["t"],
        max_bytes_per_second=1_000_000,
    )

    for t in range(1, 20):
        clock["t"] = float(t)
        logger.info("a")

    assert plugin.rate <= 0.95


def test_rate_never_drops_below_min_rate() -> None:
    clock = {"t": 0.0}
    logger, _, plugin = _logger(
        base_rate=0.1,
        min_rate=0.05,
        rng=lambda: 0.0,
        clock=lambda: clock["t"],
        max_bytes_per_second=1,
    )

    for t in range(1, 20):
        clock["t"] = float(t)
        logger.info("x" * 200)

    assert plugin.rate >= 0.05


def test_demand_that_is_dropped_by_the_budget_still_lowers_the_rate() -> None:
    """The bug this guards against: using *emitted* bytes (which stop
    growing once the budget saturates) instead of *demanded* bytes as the
    adaptivity signal would read a saturated gate as "plenty of room" and
    raise the rate, even though far more was being asked for than the
    budget allows."""
    clock = {"t": 0.0}
    logger, sink, plugin = _logger(
        base_rate=0.5, rng=lambda: 0.0, clock=lambda: clock["t"], max_bytes_per_second=10
    )

    # the very first record already exceeds the 10-byte budget, so nothing
    # is ever actually emitted this window — only demanded
    logger.info("x" * 200)
    assert sink.records == []
    clock["t"] = 2.0
    logger.info("y")

    assert plugin.rate < 0.5


def test_a_long_idle_gap_does_not_retroactively_apply_several_windows_worth() -> None:
    clock = {"t": 0.0}
    logger, _, plugin = _logger(
        base_rate=0.1, rng=lambda: 0.0, clock=lambda: clock["t"], max_bytes_per_second=1_000_000
    )

    logger.info("a")
    clock["t"] = 100.0  # a long idle gap
    logger.info("b")
    rate_after_first_roll = plugin.rate
    clock["t"] = 101.0
    logger.info("c")

    # only one more adjustment step happened, not ~100 compounding ones
    assert rate_after_first_roll < plugin.rate <= rate_after_first_roll * 1.21
