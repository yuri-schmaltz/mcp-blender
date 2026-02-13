"""Circuit breaker pattern for external API calls (MP-04)."""

import time
from enum import Enum
from typing import Any, Callable, Optional


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, calls pass through
    OPEN = "open"  # Circuit broken, calls fail immediately
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""

    pass


class CircuitBreaker:
    """Circuit breaker to prevent cascading failures from external APIs.

    States:
    - CLOSED: Normal operation, all calls pass through
    - OPEN: Too many failures, calls fail immediately
    - HALF_OPEN: After timeout, test if service recovered

    Usage:
        breaker = CircuitBreaker(failure_threshold=5, timeout=60)

        try:
            result = breaker.call(lambda: requests.get(url))
        except CircuitBreakerError:
            # Circuit is open, service unavailable
            pass
    """

    def __init__(self, failure_threshold: int = 5, timeout: int = 60, name: str = "default"):
        """Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            timeout: Seconds to wait before trying again (OPEN -> HALF_OPEN)
            name: Name for logging/debugging
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.name = name

        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = CircuitState.CLOSED

    def call(self, func: Callable[[], Any]) -> Any:
        """Execute function with circuit breaker protection.

        Args:
            func: Function to execute

        Returns:
            Result from function

        Raises:
            CircuitBreakerError: If circuit is open
            Exception: Any exception raised by func
        """
        if self.state == CircuitState.OPEN:
            # Check if timeout has elapsed
            if time.time() - self.last_failure_time >= self.timeout:
                print(f"Circuit breaker '{self.name}': OPEN -> HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
            else:
                remaining = int(self.timeout - (time.time() - self.last_failure_time))
                raise CircuitBreakerError(
                    f"Circuit breaker '{self.name}' is OPEN. "
                    f"Service unavailable. Retry in {remaining}s."
                )

        try:
            result = func()
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        """Handle successful call."""
        if self.state == CircuitState.HALF_OPEN:
            # In half-open state, need consistent successes to close
            self.success_count += 1
            if self.success_count >= 2:  # Require 2 successes to close
                print(f"Circuit breaker '{self.name}': HALF_OPEN -> CLOSED (service recovered)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success
            self.failure_count = 0

    def _on_failure(self) -> None:
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        self.success_count = 0  # Reset success count

        if self.state == CircuitState.HALF_OPEN:
            # Failed during recovery test, back to open
            print(f"Circuit breaker '{self.name}': HALF_OPEN -> OPEN (recovery failed)")
            self.state = CircuitState.OPEN
        elif self.failure_count >= self.failure_threshold:
            # Too many failures, open the circuit
            print(
                f"Circuit breaker '{self.name}': CLOSED -> OPEN "
                f"({self.failure_count} failures, threshold: {self.failure_threshold})"
            )
            self.state = CircuitState.OPEN

    def reset(self) -> None:
        """Manually reset circuit breaker to closed state."""
        print(f"Circuit breaker '{self.name}': Manual reset to CLOSED")
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None

    def get_state(self) -> dict:
        """Get current state for monitoring."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "timeout": self.timeout,
            "time_since_last_failure": (
                int(time.time() - self.last_failure_time) if self.last_failure_time else None
            ),
        }


# Global circuit breakers for external services
_circuit_breakers = {
    "polyhaven": CircuitBreaker(failure_threshold=5, timeout=60, name="polyhaven"),
    "hyper3d": CircuitBreaker(failure_threshold=3, timeout=120, name="hyper3d"),
    "sketchfab": CircuitBreaker(failure_threshold=5, timeout=60, name="sketchfab"),
}


def get_circuit_breaker(service: str) -> CircuitBreaker:
    """Get circuit breaker for a service."""
    if service not in _circuit_breakers:
        raise ValueError(f"Unknown service: {service}. Available: {list(_circuit_breakers.keys())}")
    return _circuit_breakers[service]


def get_all_circuit_states() -> dict:
    """Get states of all circuit breakers."""
    return {name: breaker.get_state() for name, breaker in _circuit_breakers.items()}
