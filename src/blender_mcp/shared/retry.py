"""Retry utilities with exponential backoff for network operations."""

import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)


def retry_with_backoff(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 30.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    on_retry: Callable[[Exception, int], None] = None,
):
    """Decorator to retry a function with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        initial_delay: Initial delay in seconds before first retry
        backoff_factor: Multiplier for delay on each retry
        max_delay: Maximum delay between retries
        exceptions: Tuple of exception types to catch and retry
        on_retry: Optional callback function called on each retry with (exception, attempt_number)

    Example:
        @retry_with_backoff(max_attempts=3, initial_delay=1.0)
        def download_file(url):
            response = requests.get(url)
            response.raise_for_status()
            return response.content
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            delay = initial_delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_attempts:
                        # Last attempt failed, raise the exception
                        logger.error(f"{func.__name__} failed after {max_attempts} attempts: {e}")
                        raise

                    # Calculate next delay
                    current_delay = min(delay, max_delay)

                    # Log retry attempt
                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt}/{max_attempts}): {e}. "
                        f"Retrying in {current_delay:.1f}s..."
                    )

                    # Call retry callback if provided
                    if on_retry:
                        try:
                            on_retry(e, attempt)
                        except Exception as callback_error:
                            logger.error(f"Retry callback failed: {callback_error}")

                    # Wait before retry
                    time.sleep(current_delay)

                    # Increase delay for next attempt
                    delay *= backoff_factor

            # Should not reach here, but just in case
            if last_exception:
                raise last_exception

        return wrapper

    return decorator


class RetryableError(Exception):
    """Base class for errors that should trigger a retry."""

    pass


class NonRetryableError(Exception):
    """Base class for errors that should NOT be retried."""

    pass


def is_transient_network_error(exception: Exception) -> bool:
    """Check if an exception is a transient network error worth retrying.

    Args:
        exception: The exception to check

    Returns:
        True if the error is transient and should be retried
    """
    import socket

    import requests

    # Socket/connection errors
    if isinstance(exception, (socket.timeout, socket.error, ConnectionError)):
        return True

    # Requests library errors
    if isinstance(exception, (requests.Timeout, requests.ConnectionError)):
        return True

    # HTTP status codes that warrant retry
    if isinstance(exception, requests.HTTPError):
        status_code = exception.response.status_code if exception.response else None
        # Retry on 5xx (server errors) and specific 4xx (rate limiting, timeout)
        retryable_codes = {408, 429, 500, 502, 503, 504}
        return status_code in retryable_codes

    return False


def retry_on_network_error(max_attempts: int = 3, initial_delay: float = 1.0):
    """Decorator to retry network operations on transient errors.

    Only retries on transient network errors. Other exceptions are raised immediately.

    Args:
        max_attempts: Maximum number of attempts
        initial_delay: Initial delay before first retry

    Example:
        @retry_on_network_error(max_attempts=3)
        def fetch_data(url):
            response = requests.get(url)
            response.raise_for_status()
            return response.json()
    """

    def should_retry(exception: Exception) -> bool:
        return is_transient_network_error(exception)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            delay = initial_delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    # Check if we should retry this exception
                    if not should_retry(e):
                        # Non-transient error, raise immediately
                        logger.error(f"{func.__name__} failed with non-retryable error: {e}")
                        raise

                    last_exception = e

                    if attempt == max_attempts:
                        logger.error(f"{func.__name__} failed after {max_attempts} attempts: {e}")
                        raise

                    current_delay = min(delay, 30.0)
                    logger.warning(
                        f"{func.__name__} network error (attempt {attempt}/{max_attempts}): {e}. "
                        f"Retrying in {current_delay:.1f}s..."
                    )

                    time.sleep(current_delay)
                    delay *= 2.0  # Exponential backoff

            if last_exception:
                raise last_exception

        return wrapper

    return decorator
