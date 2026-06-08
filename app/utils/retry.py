"""Retry helper utilities."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import time
from typing import TypeVar


T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    initial_delay_seconds: float = 0.25
    backoff_factor: float = 2.0
    retryable_status_codes: set[int] | None = None
    enable_sleep: bool = True


class RetryableOperationError(Exception):
    """Error type that carries an optional HTTP-like status code."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


def run_with_retry(func: Callable[[], T], config: RetryConfig) -> T:
    """Run a callable with exponential backoff and retryable status handling."""
    last_error: Exception | None = None
    delay_seconds = config.initial_delay_seconds
    retryable_status_codes = config.retryable_status_codes or set()

    for attempt in range(1, config.max_attempts + 1):
        try:
            return func()
        except RetryableOperationError as exc:
            last_error = exc
            if exc.status_code not in retryable_status_codes or attempt == config.max_attempts:
                raise
            if exc.retry_after_seconds is not None and exc.retry_after_seconds > delay_seconds:
                delay_seconds = exc.retry_after_seconds
        except Exception:
            raise

        if config.enable_sleep and delay_seconds > 0:
            time.sleep(delay_seconds)
        delay_seconds *= config.backoff_factor

    if last_error is not None:
        raise last_error

    raise RuntimeError("Retry helper failed without capturing an exception.")
