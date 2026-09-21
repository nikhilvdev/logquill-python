from __future__ import annotations

import pytest

from benchmarks import measure


def test_hot_path_memory_stays_within_budget() -> None:
    results = measure.measure_all()

    problems = measure.violations(results)

    assert not problems, "memory budget exceeded:\n  " + "\n  ".join(problems)


def test_the_gate_fails_on_a_seeded_regression() -> None:
    """A budget that can't fail protects nothing: feed the gate deliberately
    regressed code and confirm it reports it."""
    leaky = measure.Leaky()
    bloated = measure.Bloated()
    leaking_logger = measure.plain_logger()
    leaking_logger.use(leaky)
    bloated_logger = measure.plain_logger()
    bloated_logger.use(bloated)

    results = {
        "retained_blocks_per_call": measure.retained_blocks_per_call(leaking_logger, calls=2_000),
        "peak_bytes_plain_call": measure.peak_bytes_per_call(
            lambda: bloated_logger.info("x", **measure._META)
        ),
        # an "unbounded" queue is exactly the regression the bound exists to prevent
        "peak_bytes_stalled_burst": measure.peak_bytes_stalled_burst(
            burst=20_000, max_queue_size=1_000_000
        ),
    }

    problems = measure.violations(results, {k: measure.BUDGETS[k] for k in results})
    assert len(problems) == 3, problems


def test_a_missing_metric_is_a_failure_not_a_silent_pass() -> None:
    assert measure.violations({}) == [f"{name}: not measured" for name in measure.BUDGETS]


@pytest.mark.parametrize("policy", ["drop_oldest", "drop_newest"])
def test_stalled_burst_memory_is_set_by_the_queue_bound_not_the_burst_size(policy: str) -> None:
    small = measure.peak_bytes_stalled_burst(burst=20_000, max_queue_size=500, policy=policy)
    large = measure.peak_bytes_stalled_burst(burst=100_000, max_queue_size=500, policy=policy)

    # 5x the burst must not cost anywhere near 5x the memory
    assert large < small * 2
