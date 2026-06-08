from app.utils.retry import RetryConfig, RetryableOperationError, run_with_retry

import pytest


def test_retryable_operation_retries_until_success() -> None:
    attempts = {"count": 0}

    def flaky_operation() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RetryableOperationError("retry me", status_code=429)
        return "ok"

    result = run_with_retry(
        flaky_operation,
        RetryConfig(
            max_attempts=3,
            initial_delay_seconds=0.0,
            backoff_factor=2.0,
            retryable_status_codes={429},
            enable_sleep=False,
        ),
    )

    assert result == "ok"
    assert attempts["count"] == 3


def test_non_retryable_exception_is_not_retried() -> None:
    attempts = {"count": 0}

    def broken_operation() -> str:
        attempts["count"] += 1
        raise ValueError("bad payload")

    with pytest.raises(ValueError):
        run_with_retry(
            broken_operation,
            RetryConfig(
                max_attempts=3,
                initial_delay_seconds=0.0,
                backoff_factor=2.0,
                retryable_status_codes={429},
                enable_sleep=False,
            ),
        )

    assert attempts["count"] == 1


def test_retryable_operation_uses_retry_after_hint() -> None:
    attempts = {"count": 0}

    def flaky_operation() -> str:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RetryableOperationError("retry me", status_code=429, retry_after_seconds=0.0)
        return "ok"

    result = run_with_retry(
        flaky_operation,
        RetryConfig(
            max_attempts=2,
            initial_delay_seconds=0.0,
            backoff_factor=2.0,
            retryable_status_codes={429},
            enable_sleep=False,
        ),
    )

    assert result == "ok"
    assert attempts["count"] == 2
