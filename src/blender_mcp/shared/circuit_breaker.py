"""Circuit Breaker pattern implementation for external API calls.

This module provides a circuit breaker to prevent cascading failures when
calling external APIs like Poly Haven, Hyper3D Rodin, and Sketchfab.
"""

import logging
import time
from collections.abc import Callable
from enum import Enum
from functools import wraps
from threading import Lock
from typing import Any, Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """States of the circuit breaker."""

    CLOSED = "closed"  # Normal operation, requests flow through
    OPEN = "open"  # Circuit is tripped, requests fail fast
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open and request is rejected."""

    pass


class CircuitBreaker(Generic[T]):
    """Circuit breaker for protecting against cascading failures.

    The circuit breaker has three states:
    - CLOSED: Normal operation, requests are allowed through
    - OPEN: Service is failing, requests fail fast without calling the service
    - HALF_OPEN: Testing if service recovered by allowing limited requests

    Args:
        name: Name identifier for this circuit breaker
        failure_threshold: Number of failures before opening circuit
        recovery_timeout: Seconds to wait before trying again (OPEN -> HALF_OPEN)
        half_open_max_calls: Max calls allowed in HALF_OPEN state
        expected_exceptions: Tuple of exception types that count as failures

    Example:
        breaker = CircuitBreaker(
            name="poly_haven_api",
            failure_threshold=5,
            recovery_timeout=60,
            half_open_max_calls=1
        )

        @breaker
        def fetch_asset(url):
            response = requests.get(url)
            response.raise_for_status()
            return response.json()
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
        expected_exceptions: tuple[type[Exception], ...] = (Exception,),
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.expected_exceptions = expected_exceptions

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._half_open_calls = 0
        self._lock = Lock()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state, checking for timeout transition."""
        with self._lock:
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._transition_to_half_open()
            return self._state

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self._last_failure_time is None:
            return False
        elapsed = time.time() - self._last_failure_time
        return elapsed >= self.recovery_timeout

    def _transition_to_half_open(self) -> None:
        """Transition from OPEN to HALF_OPEN state."""
        logger.info(f"Circuit '{self.name}' transitioning to HALF_OPEN state")
        self._state = CircuitState.HALF_OPEN
        self._half_open_calls = 0

    def _transition_to_closed(self) -> None:
        """Transition to CLOSED state (normal operation)."""
        if self._state != CircuitState.CLOSED:
            logger.info(f"Circuit '{self.name}' transitioning to CLOSED state")
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0

    def _transition_to_open(self) -> None:
        """Transition to OPEN state (circuit tripped)."""
        if self._state != CircuitState.OPEN:
            logger.warning(
                f"Circuit '{self.name}' transitioning to OPEN state after "
                f"{self.failure_threshold} failures"
            )
        self._state = CircuitState.OPEN
        self._last_failure_time = time.time()
        self._half_open_calls = 0

    def record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            self._success_count += 1

            if self._state == CircuitState.HALF_OPEN:
                # Success in half-open state, close the circuit
                self._transition_to_closed()
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success
                self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        with self._lock:
            self._failure_count += 1

            if self._state == CircuitState.HALF_OPEN:
                # Failure in half-open state, back to open
                logger.warning(f"Circuit '{self.name}' failed in HALF_OPEN, reopening")
                self._transition_to_open()
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._transition_to_open()

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """Decorator to protect a function with circuit breaker logic."""

        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            current_state = self.state

            if current_state == CircuitState.OPEN:
                raise CircuitBreakerError(f"Circuit '{self.name}' is OPEN. Service unavailable.")

            if current_state == CircuitState.HALF_OPEN:
                with self._lock:
                    if self._half_open_calls >= self.half_open_max_calls:
                        raise CircuitBreakerError(
                            f"Circuit '{self.name}' is in HALF_OPEN state (max test calls reached)"
                        )
                    self._half_open_calls += 1

            try:
                result = func(*args, **kwargs)
                self.record_success()
                return result
            except self.expected_exceptions:
                self.record_failure()
                raise

        return wrapper

    def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED state."""
        with self._lock:
            logger.info(f"Circuit '{self.name}' manually reset")
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0
            self._last_failure_time = None

    def get_stats(self) -> dict[str, Any]:
        """Get current statistics for monitoring."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "last_failure_time": self._last_failure_time,
        }


# Global registry of circuit breakers for monitoring
_circuit_breakers: dict[str, CircuitBreaker] = {}
_registry_lock = Lock()


def get_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    half_open_max_calls: int = 1,
    expected_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> CircuitBreaker:
    """Get or create a named circuit breaker from the global registry.

    This ensures consistent circuit breaker instances across the application.

    Args:
        name: Unique name for the circuit breaker
        failure_threshold: Failures before opening circuit
        recovery_timeout: Seconds before attempting recovery
        half_open_max_calls: Test calls allowed in half-open state
        expected_exceptions: Exceptions that count as failures

    Returns:
        CircuitBreaker instance for the given name
    """
    with _registry_lock:
        if name not in _circuit_breakers:
            _circuit_breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
                half_open_max_calls=half_open_max_calls,
                expected_exceptions=expected_exceptions,
            )
        return _circuit_breakers[name]


def get_all_circuit_breakers() -> dict[str, CircuitBreaker]:
    """Get all registered circuit breakers."""
    with _registry_lock:
        return dict(_circuit_breakers)


def reset_all_circuit_breakers() -> None:
    """Reset all circuit breakers to CLOSED state."""
    with _registry_lock:
        for breaker in _circuit_breakers.values():
            breaker.reset()


def get_circuit_breaker_health() -> dict[str, dict[str, Any]]:
    """Get health status of all circuit breakers."""
    with _registry_lock:
        return {name: breaker.get_stats() for name, breaker in _circuit_breakers.items()}
