from datetime import datetime, timedelta

from app.worker.retry import compute_next_run


def _assert_close_to(result: datetime, expected_seconds: float, tolerance: float = 5.0) -> None:
    now = datetime.utcnow()
    lower = now + timedelta(seconds=expected_seconds - tolerance)
    upper = now + timedelta(seconds=expected_seconds + tolerance)
    assert lower <= result <= upper, f"{result} not within {tolerance}s of now+{expected_seconds}s"


def test_fixed_strategy_uses_base_delay_regardless_of_attempt():
    for attempt in (1, 2, 5):
        result = compute_next_run("fixed", base_delay=100, attempt=attempt, max_delay=10_000)
        _assert_close_to(result, 100)


def test_linear_strategy_scales_with_attempt():
    for attempt, expected_seconds in [(1, 10), (2, 20), (3, 30), (4, 40)]:
        result = compute_next_run("linear", base_delay=10, attempt=attempt, max_delay=10_000)
        _assert_close_to(result, expected_seconds)


def test_exponential_strategy_doubles_each_attempt():
    for attempt, expected_seconds in [(1, 10), (2, 20), (3, 40), (4, 80), (5, 160)]:
        result = compute_next_run("exponential", base_delay=10, attempt=attempt, max_delay=10_000)
        _assert_close_to(result, expected_seconds)


def test_fixed_strategy_capped_at_max_delay():
    result = compute_next_run("fixed", base_delay=5000, attempt=1, max_delay=3600)
    _assert_close_to(result, 3600)


def test_linear_strategy_capped_at_max_delay():
    # 100 * 100 = 10_000, should be capped down to 500.
    result = compute_next_run("linear", base_delay=100, attempt=100, max_delay=500)
    _assert_close_to(result, 500)


def test_exponential_strategy_capped_at_max_delay():
    # 60 * 2^9 = 30_720, should be capped down to 3600.
    result = compute_next_run("exponential", base_delay=60, attempt=10, max_delay=3600)
    _assert_close_to(result, 3600)


def test_uncapped_delay_is_unaffected_by_max_delay():
    result = compute_next_run("exponential", base_delay=10, attempt=2, max_delay=10_000)
    _assert_close_to(result, 20)


def test_unknown_strategy_falls_back_to_base_delay():
    result = compute_next_run("not-a-real-strategy", base_delay=42, attempt=3, max_delay=10_000)
    _assert_close_to(result, 42)
