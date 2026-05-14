"""Tests for the circuit breaker implementation."""

import time
from unittest.mock import Mock, patch

import pytest

from src.blender_mcp.shared.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitState,
    get_all_circuit_breakers,
    get_circuit_breaker,
    get_circuit_breaker_health,
    reset_all_circuit_breakers,
)


class TestCircuitBreaker:
    """Test cases for CircuitBreaker class."""

    def test_initial_state_is_closed(self):
        """Test that circuit breaker starts in CLOSED state."""
        breaker = CircuitBreaker(name="test")
        assert breaker.state == CircuitState.CLOSED

    def test_success_keeps_circuit_closed(self):
        """Test that successful calls keep the circuit closed."""
        breaker = CircuitBreaker(name="test", failure_threshold=3)

        @breaker
        def success_func():
            return "success"

        result = success_func()
        assert result == "success"
        assert breaker.state == CircuitState.CLOSED

    def test_failures_below_threshold_keep_closed(self):
        """Test that failures below threshold keep circuit closed."""
        breaker = CircuitBreaker(name="test", failure_threshold=3)

        @breaker
        def fail_func():
            raise ValueError("error")

        for _ in range(2):  # Less than threshold
            with pytest.raises(ValueError):
                fail_func()

        assert breaker.state == CircuitState.CLOSED

    def test_failures_at_threshold_open_circuit(self):
        """Test that failures at threshold open the circuit."""
        breaker = CircuitBreaker(name="test", failure_threshold=3)

        @breaker
        def fail_func():
            raise ValueError("error")

        for _ in range(3):  # At threshold
            with pytest.raises(ValueError):
                fail_func()

        assert breaker.state == CircuitState.OPEN

    def test_open_circuit_rejects_calls(self):
        """Test that open circuit rejects calls immediately."""
        breaker = CircuitBreaker(name="test", failure_threshold=1)

        @breaker
        def fail_func():
            raise ValueError("error")

        # Open the circuit
        with pytest.raises(ValueError):
            fail_func()

        assert breaker.state == CircuitState.OPEN

        # Should reject without calling function
        with pytest.raises(CircuitBreakerError):
            fail_func()

    def test_recovery_timeout_transitions_to_half_open(self):
        """Test that after recovery timeout, circuit transitions to HALF_OPEN."""
        breaker = CircuitBreaker(
            name="test", failure_threshold=1, recovery_timeout=0.1
        )

        @breaker
        def fail_func():
            raise ValueError("error")

        # Open the circuit
        with pytest.raises(ValueError):
            fail_func()

        assert breaker.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(0.15)

        # Next access should transition to HALF_OPEN
        assert breaker.state == CircuitState.HALF_OPEN

    def test_half_open_success_closes_circuit(self):
        """Test that success in HALF_OPEN state closes the circuit."""
        breaker = CircuitBreaker(
            name="test", failure_threshold=1, recovery_timeout=0.1
        )

        call_count = 0

        @breaker
        def sometimes_fails():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("first call fails")
            return "success"

        # First call fails and opens circuit
        with pytest.raises(ValueError):
            sometimes_fails()

        assert breaker.state == CircuitState.OPEN

        # Wait for recovery
        time.sleep(0.15)
        assert breaker.state == CircuitState.HALF_OPEN

        # Successful call should close circuit
        result = sometimes_fails()
        assert result == "success"
        assert breaker.state == CircuitState.CLOSED

    def test_half_open_failure_reopens_circuit(self):
        """Test that failure in HALF_OPEN state reopens the circuit."""
        breaker = CircuitBreaker(
            name="test", failure_threshold=1, recovery_timeout=0.1
        )

        @breaker
        def always_fails():
            raise ValueError("error")

        # Open the circuit
        with pytest.raises(ValueError):
            always_fails()

        # Wait for recovery
        time.sleep(0.15)
        assert breaker.state == CircuitState.HALF_OPEN

        # Failure in half-open should reopen
        with pytest.raises(ValueError):
            always_fails()

        assert breaker.state == CircuitState.OPEN

    def test_half_open_max_calls_limit(self):
        """Test that half-open state respects max calls limit."""
        breaker = CircuitBreaker(
            name="test",
            failure_threshold=1,
            recovery_timeout=0.1,
            half_open_max_calls=1,
        )

        call_count = 0

        @breaker
        def slow_success():
            nonlocal call_count
            call_count += 1
            time.sleep(0.05)
            return "success"

        # Open the circuit
        with pytest.raises(Exception):
            breaker(lambda: (_ for _ in ()).throw(ValueError("error")))()

        # Wait for recovery
        time.sleep(0.15)
        assert breaker.state == CircuitState.HALF_OPEN

        # First call succeeds
        result = slow_success()
        assert result == "success"

        # Circuit should be closed after success
        assert breaker.state == CircuitState.CLOSED

    def test_manual_reset(self):
        """Test manual reset of circuit breaker."""
        breaker = CircuitBreaker(name="test", failure_threshold=1)

        @breaker
        def fail_func():
            raise ValueError("error")

        # Open the circuit
        with pytest.raises(ValueError):
            fail_func()

        assert breaker.state == CircuitState.OPEN

        # Manual reset
        breaker.reset()
        assert breaker.state == CircuitState.CLOSED

    def test_get_stats(self):
        """Test getting statistics from circuit breaker."""
        breaker = CircuitBreaker(name="test_stats", failure_threshold=3)

        @breaker
        def mixed_func(fail=False):
            if fail:
                raise ValueError("error")
            return "success"

        mixed_func(fail=False)
        
        # Catch the exceptions for failing calls
        for _ in range(2):
            try:
                mixed_func(fail=True)
            except ValueError:
                pass

        stats = breaker.get_stats()
        assert stats["name"] == "test_stats"
        assert stats["failure_count"] == 2
        assert stats["success_count"] == 1
        assert stats["failure_threshold"] == 3
        assert stats["state"] == CircuitState.CLOSED.value

    def test_different_exception_types(self):
        """Test that only expected exceptions count as failures."""
        breaker = CircuitBreaker(
            name="test", failure_threshold=1, expected_exceptions=(ValueError,)
        )

        @breaker
        def raise_type_error():
            raise TypeError("not counted")

        # TypeError should not be caught by circuit breaker
        with pytest.raises(TypeError):
            raise_type_error()

        # Circuit should still be closed
        assert breaker.state == CircuitState.CLOSED


class TestCircuitBreakerRegistry:
    """Test cases for global circuit breaker registry."""

    def setup_method(self):
        """Clean up registry before each test."""
        reset_all_circuit_breakers()

    def teardown_method(self):
        """Clean up registry after each test."""
        reset_all_circuit_breakers()

    def test_get_circuit_breaker_creates_new(self):
        """Test that get_circuit_breaker creates new instance."""
        breaker = get_circuit_breaker(name="test_api")
        assert breaker is not None
        assert breaker.name == "test_api"

    def test_get_circuit_breaker_returns_same_instance(self):
        """Test that get_circuit_breaker returns same instance for same name."""
        breaker1 = get_circuit_breaker(name="test_api")
        breaker2 = get_circuit_breaker(name="test_api")
        assert breaker1 is breaker2

    def test_get_circuit_breaker_different_instances_for_different_names(self):
        """Test that different names get different instances."""
        breaker1 = get_circuit_breaker(name="api1")
        breaker2 = get_circuit_breaker(name="api2")
        assert breaker1 is not breaker2
        assert breaker1.name == "api1"
        assert breaker2.name == "api2"

    def test_get_all_circuit_breakers(self):
        """Test getting all registered circuit breakers."""
        # Get count before adding new breakers
        initial_breakers = get_all_circuit_breakers()
        initial_count = len(initial_breakers)
        
        get_circuit_breaker(name="test_api1")
        get_circuit_breaker(name="test_api2")

        all_breakers = get_all_circuit_breakers()
        assert len(all_breakers) == initial_count + 2
        assert "test_api1" in all_breakers
        assert "test_api2" in all_breakers

    def test_reset_all_circuit_breakers(self):
        """Test resetting all circuit breakers."""
        breaker = get_circuit_breaker(name="test_reset", failure_threshold=1)

        # Manually set to open state
        breaker._transition_to_open()
        assert breaker.state == CircuitState.OPEN

        reset_all_circuit_breakers()
        assert breaker.state == CircuitState.CLOSED

    def test_get_circuit_breaker_health(self):
        """Test getting health status of all circuit breakers."""
        reset_all_circuit_breakers()
        
        breaker = get_circuit_breaker(name="test_api")

        health = get_circuit_breaker_health()
        assert "test_api" in health
        assert health["test_api"]["name"] == "test_api"
        assert health["test_api"]["state"] == CircuitState.CLOSED.value


class TestCircuitBreakerIntegration:
    """Integration tests for circuit breaker with real scenarios."""

    def test_circuit_breaker_protects_network_call(self):
        """Test circuit breaker protects against failing network calls."""
        breaker = CircuitBreaker(
            name="mock_api",
            failure_threshold=3,
            recovery_timeout=0.1,
            expected_exceptions=(Exception,),
        )

        call_count = 0

        @breaker
        def mock_network_call():
            nonlocal call_count
            call_count += 1
            if call_count <= 5:
                raise ConnectionError("Network error")
            return {"data": "success"}

        # First 3 calls fail and open circuit
        for i in range(3):
            with pytest.raises(ConnectionError):
                mock_network_call()

        assert breaker.state == CircuitState.OPEN

        # Next call should be rejected immediately (call_count stays at 3)
        with pytest.raises(CircuitBreakerError):
            mock_network_call()

        assert call_count == 3  # Function not called

    def test_circuit_breaker_with_retry_pattern(self):
        """Test circuit breaker works well with retry pattern."""
        from src.blender_mcp.shared.retry import retry_with_backoff

        breaker = CircuitBreaker(
            name="retryable_api_test",
            failure_threshold=5,  # High threshold to avoid opening during retries
            recovery_timeout=0.1,
        )

        call_count = 0

        @breaker
        @retry_with_backoff(max_attempts=3, initial_delay=0.01)
        def flaky_api():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TimeoutError("timeout")
            return "success"

        # Should retry and eventually succeed
        result = flaky_api()
        assert result == "success"
        assert call_count >= 3
