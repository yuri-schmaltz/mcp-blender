"""Tests for the health check implementation."""

import json
import socket
import threading
import time
from unittest.mock import Mock, patch

import pytest

from src.blender_mcp.shared.health_check import (
    ConnectionHealthChecker,
    HealthCheckResult,
    HealthStatus,
    get_health_checker,
    get_health_status,
    start_health_checker,
    stop_health_checker,
)


class MockServer:
    """Simple mock server for testing health checks."""

    def __init__(self, host="localhost", port=9999, response_delay=0.01):
        self.host = host
        self.port = port
        self.response_delay = response_delay
        self.running = False
        self.server_socket = None
        self.thread = None
        self.request_count = 0
        self.fail_requests = False

    def start(self):
        """Start the mock server."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.server_socket.settimeout(0.5)
        self.running = True
        self.thread = threading.Thread(target=self._accept_loop, daemon=True)
        self.thread.start()
        time.sleep(0.01)  # Give server time to start

    def stop(self):
        """Stop the mock server."""
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        if self.thread:
            self.thread.join(timeout=1.0)

    def _accept_loop(self):
        """Accept and handle connections."""
        while self.running:
            try:
                client_socket, addr = self.server_socket.accept()
                self._handle_client(client_socket)
            except TimeoutError:
                continue
            except Exception:
                break

    def _handle_client(self, client_socket):
        """Handle a client connection."""
        try:
            client_socket.settimeout(2.0)
            data = client_socket.recv(4096)

            if data:
                self.request_count += 1
                time.sleep(self.response_delay)

                if self.fail_requests:
                    # Don't respond or send error
                    pass
                else:
                    try:
                        request = json.loads(data.decode("utf-8"))
                        if request.get("type") == "ping":
                            response = b'{"type": "pong"}\n'
                            client_socket.sendall(response)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        pass
        except Exception:
            pass
        finally:
            try:
                client_socket.close()
            except Exception:
                pass


class TestHealthCheckResult:
    """Test cases for HealthCheckResult dataclass."""

    def test_healthy_result(self):
        """Test creating a healthy result."""
        result = HealthCheckResult(status=HealthStatus.HEALTHY, response_time_ms=50.0)
        assert result.status == HealthStatus.HEALTHY
        assert result.response_time_ms == 50.0
        assert result.error is None

    def test_unhealthy_result(self):
        """Test creating an unhealthy result."""
        result = HealthCheckResult(status=HealthStatus.UNHEALTHY, error="Connection failed")
        assert result.status == HealthStatus.UNHEALTHY
        assert result.error == "Connection failed"
        assert result.response_time_ms is None


class TestConnectionHealthChecker:
    """Test cases for ConnectionHealthChecker class."""

    @pytest.fixture
    def mock_server(self):
        """Create and cleanup a mock server."""
        server = MockServer(port=9998)
        server.start()
        yield server
        server.stop()

    def test_initial_state_is_unknown(self):
        """Test that checker starts with UNKNOWN status."""
        checker = ConnectionHealthChecker(host="localhost", port=9997)
        assert checker.status == HealthStatus.UNKNOWN
        assert not checker.is_healthy

    def test_successful_health_check(self, mock_server):
        """Test successful health check returns HEALTHY status."""
        checker = ConnectionHealthChecker(
            host=mock_server.host,
            port=mock_server.port,
            timeout=2.0,
            degraded_threshold_ms=1000.0,
        )

        result = checker.check_health()

        assert result.status == HealthStatus.HEALTHY
        assert result.response_time_ms is not None
        assert result.response_time_ms > 0
        assert result.error is None
        assert checker.is_healthy

    def test_failed_health_check_no_server(self):
        """Test health check fails when no server is running."""
        checker = ConnectionHealthChecker(
            host="localhost", port=9996, timeout=0.5, unhealthy_threshold=1
        )

        result = checker.check_health()

        assert result.status in [HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]
        assert result.error is not None
        assert not checker.is_healthy

    def test_consecutive_failures_lead_to_unhealthy(self):
        """Test that consecutive failures transition to UNHEALTHY."""
        checker = ConnectionHealthChecker(
            host="localhost", port=9995, timeout=0.3, unhealthy_threshold=3
        )

        # First two failures should be DEGRADED
        result1 = checker.check_health()
        assert result1.status == HealthStatus.DEGRADED

        result2 = checker.check_health()
        assert result2.status == HealthStatus.DEGRADED

        # Third failure should be UNHEALTHY
        result3 = checker.check_health()
        assert result3.status == HealthStatus.UNHEALTHY

    def test_stats_tracking(self, mock_server):
        """Test that statistics are tracked correctly."""
        checker = ConnectionHealthChecker(host=mock_server.host, port=mock_server.port, timeout=2.0)

        # Perform some checks
        checker.check_health()
        checker.check_health()

        stats = checker.stats
        assert stats["total_checks"] == 2
        assert stats["successful_checks"] == 2
        assert stats["failed_checks"] == 0
        assert stats["success_rate"] == 1.0
        assert stats["status"] == HealthStatus.HEALTHY.value

    def test_reset_stats(self, mock_server):
        """Test resetting statistics."""
        checker = ConnectionHealthChecker(host=mock_server.host, port=mock_server.port, timeout=2.0)

        checker.check_health()
        checker.reset_stats()

        stats = checker.stats
        assert stats["total_checks"] == 0
        assert stats["successful_checks"] == 0
        assert stats["failed_checks"] == 0
        assert stats["status"] == HealthStatus.UNKNOWN.value

    def test_status_change_callback(self, mock_server):
        """Test that status change callback is invoked."""
        status_changes = []

        def on_status_change(status):
            status_changes.append(status)

        checker = ConnectionHealthChecker(
            host="localhost",
            port=9994,
            timeout=0.3,
            unhealthy_threshold=1,
            on_status_change=on_status_change,
        )

        # First check fails
        checker.check_health()

        # Should have triggered status change from UNKNOWN to DEGRADED
        assert len(status_changes) >= 1

    def test_background_thread_start_stop(self, mock_server):
        """Test starting and stopping background health check thread."""
        checker = ConnectionHealthChecker(
            host=mock_server.host,
            port=mock_server.port,
            check_interval=0.5,
            timeout=2.0,
        )

        assert checker._thread is None
        assert not checker._running

        checker.start()
        assert checker._thread is not None
        assert checker._running

        time.sleep(0.6)  # Let it run for a bit

        checker.stop()
        assert not checker._running

    def test_degraded_status_on_slow_response(self):
        """Test that slow responses result in DEGRADED status."""
        # Create server with slow response
        server = MockServer(port=9993, response_delay=0.5)
        server.start()

        try:
            checker = ConnectionHealthChecker(
                host=server.host,
                port=server.port,
                timeout=2.0,
                degraded_threshold_ms=100.0,  # 100ms threshold
            )

            result = checker.check_health()

            # Should be degraded due to slow response
            assert result.status == HealthStatus.DEGRADED
            assert result.response_time_ms > 100.0
        finally:
            server.stop()


class TestHealthCheckerRegistry:
    """Test cases for global health checker registry."""

    def teardown_method(self):
        """Clean up registry after each test."""
        stop_health_checker()

    def test_get_health_checker_creates_new(self):
        """Test that get_health_checker creates new instance."""
        checker = get_health_checker(host="localhost", port=9992)
        assert checker is not None
        assert checker.host == "localhost"
        assert checker.port == 9992

    def test_get_health_checker_returns_same_instance(self):
        """Test that get_health_checker returns same instance."""
        checker1 = get_health_checker(host="localhost", port=9991)
        checker2 = get_health_checker(host="localhost", port=9991)
        assert checker1 is checker2

    def test_start_health_checker(self):
        """Test starting health checker via registry function."""
        checker = start_health_checker(host="localhost", port=9990, check_interval=1.0)
        assert checker is not None
        assert checker._running

        stop_health_checker()
        assert not checker._running

    def test_get_health_status(self):
        """Test getting health status from registry."""
        # Without initialization
        status = get_health_status()
        assert status["status"] == HealthStatus.UNKNOWN.value
        assert "error" in status

        # With initialization
        checker = get_health_checker(host="localhost", port=9989)
        status = get_health_status()
        assert status["host"] == "localhost"
        assert status["port"] == 9989


class TestHealthCheckerIntegration:
    """Integration tests for health checker."""

    def test_full_health_check_lifecycle(self):
        """Test complete lifecycle of health checking."""
        server = MockServer(port=9988)
        server.start()

        try:
            status_changes = []
            reconnect_called = False

            def on_status_change(status):
                status_changes.append(status)

            def on_reconnect():
                nonlocal reconnect_called
                reconnect_called = True

            checker = ConnectionHealthChecker(
                host=server.host,
                port=server.port,
                check_interval=0.5,
                timeout=2.0,
                unhealthy_threshold=2,
                on_status_change=on_status_change,
                on_reconnect_needed=on_reconnect,
            )

            # Start healthy
            result = checker.check_health()
            assert result.status == HealthStatus.HEALTHY

            # Stop server
            server.stop()
            time.sleep(0.1)

            # Check should fail
            result = checker.check_health()
            assert result.status in [HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]
            assert result.error is not None

        finally:
            server.stop()

    def test_recovery_after_failure(self):
        """Test that checker detects recovery after failure."""
        server = MockServer(port=9987)

        try:
            checker = ConnectionHealthChecker(
                host=server.host,
                port=server.port,
                timeout=0.5,
                unhealthy_threshold=1,
            )

            # Initial check fails (no server)
            result1 = checker.check_health()
            assert result1.status in [HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]

            # Start server
            server.start()
            time.sleep(0.1)

            # Check should succeed
            result2 = checker.check_health()
            assert result2.status == HealthStatus.HEALTHY
            assert result2.error is None

        finally:
            server.stop()
