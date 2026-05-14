"""Health check utilities for monitoring Blender connection.

This module provides health check functionality to proactively detect
connection issues with Blender and enable automatic reconnection.
"""

import logging
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from threading import Lock, Thread
from typing import Any

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status of the Blender connection."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """Result of a health check operation."""

    status: HealthStatus
    response_time_ms: float | None = None
    error: str | None = None
    details: dict[str, Any] | None = None
    timestamp: float | None = None


class ConnectionHealthChecker:
    """Proactive health checker for Blender socket connection.

    Monitors the connection health by sending periodic ping commands
    and tracking response times. Automatically detects disconnections
    and can trigger reconnection logic.

    Args:
        host: Blender host address
        port: Blender port number
        check_interval: Seconds between health checks
        timeout: Socket timeout for health checks
        unhealthy_threshold: Consecutive failures before marking unhealthy
        degraded_threshold: Response time (ms) above which connection is degraded
        on_status_change: Callback when health status changes
        on_reconnect_needed: Callback when reconnection is needed

    Example:
        checker = ConnectionHealthChecker(
            host="localhost",
            port=9876,
            check_interval=10.0,
            on_status_change=lambda status: print(f\"Status: {status}\"),
            on_reconnect_needed=lambda: reconnect()
        )
        checker.start()
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 9876,
        check_interval: float = 10.0,
        timeout: float = 5.0,
        unhealthy_threshold: int = 3,
        degraded_threshold_ms: float = 1000.0,
        on_status_change: Callable[[HealthStatus], None] | None = None,
        on_reconnect_needed: Callable[[], None] | None = None,
    ):
        self.host = host
        self.port = port
        self.check_interval = check_interval
        self.timeout = timeout
        self.unhealthy_threshold = unhealthy_threshold
        self.degraded_threshold_ms = degraded_threshold_ms

        self._on_status_change = on_status_change
        self._on_reconnect_needed = on_reconnect_needed

        self._status = HealthStatus.UNKNOWN
        self._consecutive_failures = 0
        self._last_check_time: float | None = None
        self._last_response_time_ms: float | None = None
        self._running = False
        self._thread: Thread | None = None
        self._lock = Lock()

        # Statistics
        self._total_checks = 0
        self._successful_checks = 0
        self._failed_checks = 0

    @property
    def status(self) -> HealthStatus:
        """Get current health status."""
        with self._lock:
            return self._status

    @property
    def is_healthy(self) -> bool:
        """Check if connection is currently healthy."""
        return self.status == HealthStatus.HEALTHY

    @property
    def stats(self) -> dict[str, Any]:
        """Get health check statistics."""
        with self._lock:
            return {
                "status": self._status.value,
                "host": self.host,
                "port": self.port,
                "check_interval": self.check_interval,
                "consecutive_failures": self._consecutive_failures,
                "last_check_time": self._last_check_time,
                "last_response_time_ms": self._last_response_time_ms,
                "total_checks": self._total_checks,
                "successful_checks": self._successful_checks,
                "failed_checks": self._failed_checks,
                "success_rate": (
                    self._successful_checks / self._total_checks if self._total_checks > 0 else 0.0
                ),
            }

    def check_health(self) -> HealthCheckResult:
        """Perform a single health check on the Blender connection.

        Sends a simple ping command to Blender and measures response time.

        Returns:
            HealthCheckResult with status and metrics
        """
        start_time = time.time()
        error = None
        response_time_ms = None

        try:
            # Create a test socket connection
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)

            try:
                sock.connect((self.host, self.port))

                # Send a simple ping command
                ping_cmd = b'{"type": "ping", "params": {}}\n'
                sock.sendall(ping_cmd)

                # Wait for response
                response = b""
                recv_start = time.time()

                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response += chunk

                    # Check if we received a complete response
                    if response.endswith(b"\n"):
                        try:
                            response_data = json.loads(response.decode("utf-8"))
                            if response_data.get("type") == "pong":
                                response_time_ms = (time.time() - start_time) * 1000
                                break
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            pass

                    # Timeout for response
                    if time.time() - recv_start > self.timeout:
                        raise TimeoutError("Response timeout")

            finally:
                sock.close()

        except TimeoutError as e:
            error = f"Connection timeout: {e}"
        except ConnectionRefusedError as e:
            error = f"Connection refused: {e}"
        except OSError as e:
            error = f"Socket error: {e}"
        except Exception as e:
            error = f"Unexpected error: {e}"

        # Update statistics
        with self._lock:
            self._total_checks += 1
            self._last_check_time = time.time()

            if error:
                self._failed_checks += 1
                self._consecutive_failures += 1
                self._last_response_time_ms = None
            else:
                self._successful_checks += 1
                self._consecutive_failures = 0
                self._last_response_time_ms = response_time_ms

        # Determine status
        if error:
            if self._consecutive_failures >= self.unhealthy_threshold:
                new_status = HealthStatus.UNHEALTHY
            else:
                new_status = HealthStatus.DEGRADED
        elif response_time_ms and response_time_ms > self.degraded_threshold_ms:
            new_status = HealthStatus.DEGRADED
        else:
            new_status = HealthStatus.HEALTHY

        # Update status and notify callbacks
        with self._lock:
            status_changed = self._status != new_status
            self._status = new_status

        if status_changed:
            logger.info(f"Blender connection health changed to {new_status.value}")
            if self._on_status_change:
                try:
                    self._on_status_change(new_status)
                except Exception as e:
                    logger.error(f"Status change callback failed: {e}")

            if new_status == HealthStatus.UNHEALTHY and self._on_reconnect_needed:
                try:
                    self._on_reconnect_needed()
                except Exception as e:
                    logger.error(f"Reconnect callback failed: {e}")

        return HealthCheckResult(
            status=new_status,
            response_time_ms=response_time_ms,
            error=error,
            timestamp=self._last_check_time,
        )

    def _run_loop(self) -> None:
        """Background thread loop for continuous health checking."""
        logger.info(
            f"Starting health check loop for {self.host}:{self.port} "
            f"(interval={self.check_interval}s)"
        )

        while self._running:
            try:
                self.check_health()
            except Exception as e:
                logger.error(f"Health check loop error: {e}")

            # Sleep in small increments to allow quick shutdown
            sleep_interval = min(0.5, self.check_interval)
            for _ in range(int(self.check_interval / sleep_interval)):
                if not self._running:
                    break
                time.sleep(sleep_interval)

        logger.info("Health check loop stopped")

    def start(self) -> None:
        """Start the background health check thread."""
        with self._lock:
            if self._running:
                logger.warning("Health checker already running")
                return

            self._running = True
            self._thread = Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            logger.info("Health checker started")

    def stop(self) -> None:
        """Stop the background health check thread."""
        with self._lock:
            if not self._running:
                return
            self._running = False

        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

        logger.info("Health checker stopped")

    def reset_stats(self) -> None:
        """Reset all statistics."""
        with self._lock:
            self._total_checks = 0
            self._successful_checks = 0
            self._failed_checks = 0
            self._consecutive_failures = 0
            self._last_check_time = None
            self._last_response_time_ms = None
            self._status = HealthStatus.UNKNOWN


# Import json at module level for use in check_health
import json  # noqa: E402

# Global health checker instance
_health_checker: ConnectionHealthChecker | None = None
_health_checker_lock = Lock()


def get_health_checker(
    host: str = "localhost",
    port: int = 9876,
    check_interval: float = 10.0,
    timeout: float = 5.0,
    unhealthy_threshold: int = 3,
    degraded_threshold_ms: float = 1000.0,
    on_status_change: Callable[[HealthStatus], None] | None = None,
    on_reconnect_needed: Callable[[], None] | None = None,
) -> ConnectionHealthChecker:
    """Get or create a global health checker instance.

    Args:
        host: Blender host address
        port: Blender port number
        check_interval: Seconds between health checks
        timeout: Socket timeout for health checks
        unhealthy_threshold: Consecutive failures before marking unhealthy
        degraded_threshold_ms: Response time (ms) above which connection is degraded
        on_status_change: Callback when health status changes
        on_reconnect_needed: Callback when reconnection is needed

    Returns:
        ConnectionHealthChecker instance
    """
    global _health_checker

    with _health_checker_lock:
        if _health_checker is None:
            _health_checker = ConnectionHealthChecker(
                host=host,
                port=port,
                check_interval=check_interval,
                timeout=timeout,
                unhealthy_threshold=unhealthy_threshold,
                degraded_threshold_ms=degraded_threshold_ms,
                on_status_change=on_status_change,
                on_reconnect_needed=on_reconnect_needed,
            )
        elif (
            _health_checker.host != host
            or _health_checker.port != port
            or _health_checker.check_interval != check_interval
        ):
            # Configuration changed, recreate
            _health_checker.stop()
            _health_checker = ConnectionHealthChecker(
                host=host,
                port=port,
                check_interval=check_interval,
                timeout=timeout,
                unhealthy_threshold=unhealthy_threshold,
                degraded_threshold_ms=degraded_threshold_ms,
                on_status_change=on_status_change,
                on_reconnect_needed=on_reconnect_needed,
            )

        return _health_checker


def start_health_checker(
    host: str = "localhost",
    port: int = 9876,
    check_interval: float = 10.0,
    **kwargs: Any,
) -> ConnectionHealthChecker:
    """Start the global health checker.

    Args:
        host: Blender host address
        port: Blender port number
        check_interval: Seconds between health checks
        **kwargs: Additional arguments passed to get_health_checker

    Returns:
        Running ConnectionHealthChecker instance
    """
    checker = get_health_checker(host=host, port=port, check_interval=check_interval, **kwargs)
    checker.start()
    return checker


def stop_health_checker() -> None:
    """Stop the global health checker."""
    global _health_checker

    with _health_checker_lock:
        if _health_checker:
            _health_checker.stop()
            _health_checker = None


def get_health_status() -> dict[str, Any]:
    """Get current health status from the global checker.

    Returns:
        Dictionary with health status and statistics
    """
    global _health_checker

    with _health_checker_lock:
        if _health_checker:
            return _health_checker.stats
        return {"status": HealthStatus.UNKNOWN.value, "error": "Health checker not initialized"}
