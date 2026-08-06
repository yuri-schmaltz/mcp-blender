"""Circuit breaker pattern for external API calls (addon-side).

This module provides a standalone circuit breaker for the Blender addon side.
It mirrors the API of `src/blender_mcp/shared/circuit_breaker.py` but lives
in the addon package because Blender's Python environment cannot reliably
import from the MCP server package.

The circuit breaker protects external HTTP calls (Poly Haven, Sketchfab,
AmbientCG) from cascading failures: after a configurable number of
consecutive failures, the circuit opens and subsequent calls fail fast
until a cooldown period elapses.

Usage:
    from .circuit_breaker import get_circuit_breaker, CircuitBreakerError

    breaker = get_circuit_breaker("polyhaven")
    try:
        result = breaker.call(lambda: requests.get(url, timeout=10))
    except CircuitBreakerError:
        # Circuit is open — service unavailable, fail fast
        return {"error": "Poly Haven temporarily unavailable (circuit open)"}
"""

import time
from collections.abc import Callable
from enum import Enum
from typing import Any


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, calls pass through
    OPEN = "open"  # Circuit broken, calls fail immediately
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreakerError(Exception):
    """Raised when the circuit is open and a call is rejected without being attempted."""

    pass


class CircuitBreaker:
    """Circuit breaker to prevent cascading failures from external APIs.

    States:
    - CLOSED: Normal operation, all calls pass through.
    - OPEN: Too many failures, calls fail fast (raise CircuitBreakerError).
    - HALF_OPEN: After timeout, test if service recovered. Two consecutive
      successes close the circuit; a single failure re-opens it.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: int = 60,
        name: str = "default",
    ):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.name = name

        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: float | None = None
        self.state = CircuitState.CLOSED

    def call(self, func: Callable[[], Any]) -> Any:
        """Execute ``func`` under circuit-breaker protection."""
        if self.state == CircuitState.OPEN:
            if self.last_failure_time is not None and (
                time.time() - self.last_failure_time >= self.timeout
            ):
                print(
                    f"[blender-mcp] Circuit '{self.name}': OPEN -> HALF_OPEN (cooldown elapsed)"
                )
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
            else:
                remaining = (
                    int(
                        self.timeout
                        - (time.time() - (self.last_failure_time or time.time()))
                    )
                    if self.last_failure_time is not None
                    else self.timeout
                )
                raise CircuitBreakerError(
                    f"Circuit '{self.name}' is OPEN. Service unavailable. "
                    f"Retry in {max(remaining, 0)}s."
                )

        try:
            result = func()
        except Exception:
            self._on_failure()
            raise
        else:
            self._on_success()
            return result

    def _on_success(self) -> None:
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= 2:
                print(
                    f"[blender-mcp] Circuit '{self.name}': HALF_OPEN -> CLOSED (service recovered)"
                )
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0

    def _on_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()
        self.success_count = 0

        if self.state == CircuitState.HALF_OPEN:
            print(
                f"[blender-mcp] Circuit '{self.name}': HALF_OPEN -> OPEN (recovery test failed)"
            )
            self.state = CircuitState.OPEN
        elif self.failure_count >= self.failure_threshold:
            print(
                f"[blender-mcp] Circuit '{self.name}': CLOSED -> OPEN "
                f"({self.failure_count} failures, threshold: {self.failure_threshold})"
            )
            self.state = CircuitState.OPEN

    def reset(self) -> None:
        """Manually reset the circuit to CLOSED state."""
        print(f"[blender-mcp] Circuit '{self.name}': manual reset to CLOSED")
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None

    def get_state(self) -> dict:
        """Return the current breaker state as a dict (for diagnostics)."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "timeout": self.timeout,
            "time_since_last_failure": (
                int(time.time() - self.last_failure_time)
                if self.last_failure_time is not None
                else None
            ),
        }


# Per-service breakers — failure_threshold=5, cooldown=60s match the
# values used on the MCP-server side and were the de-facto choice from
# the v0.x hardening work.
_circuit_breakers: dict[str, CircuitBreaker] = {
    "polyhaven": CircuitBreaker(failure_threshold=5, timeout=60, name="polyhaven"),
    "sketchfab": CircuitBreaker(failure_threshold=5, timeout=60, name="sketchfab"),
    "ambientcg": CircuitBreaker(failure_threshold=5, timeout=60, name="ambientcg"),
}


def get_circuit_breaker(service: str) -> CircuitBreaker:
    """Return the breaker registered for ``service``."""
    if service not in _circuit_breakers:
        raise ValueError(
            f"Unknown service: {service!r}. "
            f"Known services: {sorted(_circuit_breakers.keys())}"
        )
    return _circuit_breakers[service]


def get_all_circuit_states() -> dict:
    """Return a snapshot of every registered breaker's state."""
    return {name: breaker.get_state() for name, breaker in _circuit_breakers.items()}


def reset_all_circuits() -> None:
    """Reset every registered breaker to CLOSED (used by tests and admin)."""
    for breaker in _circuit_breakers.values():
        breaker.reset()
