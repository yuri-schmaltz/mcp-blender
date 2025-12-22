"""Tests for circuit breaker pattern."""

import time
import pytest
from blender_mcp.shared.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitState,
    get_circuit_breaker,
)


class TestCircuitBreaker:
    """Test circuit breaker functionality."""
    
    def test_initial_state_is_closed(self):
        """Circuit breaker should start in CLOSED state."""
        breaker = CircuitBreaker()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0
    
    def test_successful_calls_stay_closed(self):
        """Successful calls should keep circuit CLOSED."""
        breaker = CircuitBreaker(failure_threshold=3)
        
        for _ in range(5):
            result = breaker.call(lambda: "success")
            assert result == "success"
            assert breaker.state == CircuitState.CLOSED
    
    def test_failures_open_circuit(self):
        """Exceeding failure threshold should open circuit."""
        breaker = CircuitBreaker(failure_threshold=3)
        
        # Fail 3 times
        for i in range(3):
            with pytest.raises(ValueError):
                breaker.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        
        # Circuit should now be OPEN
        assert breaker.state == CircuitState.OPEN
        assert breaker.failure_count == 3
    
    def test_open_circuit_raises_error(self):
        """Open circuit should raise CircuitBreakerError immediately."""
        breaker = CircuitBreaker(failure_threshold=2, timeout=60)
        
        # Trigger failures to open circuit
        for _ in range(2):
            with pytest.raises(ValueError):
                breaker.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        
        # Next call should fail immediately with CircuitBreakerError
        with pytest.raises(CircuitBreakerError) as exc_info:
            breaker.call(lambda: "should not execute")
        
        assert "OPEN" in str(exc_info.value)
        assert breaker.state == CircuitState.OPEN
    
    def test_half_open_after_timeout(self):
        """Circuit should transition to HALF_OPEN after timeout."""
        breaker = CircuitBreaker(failure_threshold=2, timeout=1)
        
        # Open the circuit
        for _ in range(2):
            with pytest.raises(ValueError):
                breaker.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        
        assert breaker.state == CircuitState.OPEN
        
        # Wait for timeout
        time.sleep(1.1)
        
        # Next call should transition to HALF_OPEN and execute
        result = breaker.call(lambda: "recovered")
        assert result == "recovered"
        assert breaker.state == CircuitState.HALF_OPEN
    
    def test_half_open_closes_on_success(self):
        """HALF_OPEN should close after 2 consecutive successes."""
        breaker = CircuitBreaker(failure_threshold=2, timeout=1)
        
        # Open circuit
        for _ in range(2):
            with pytest.raises(ValueError):
                breaker.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        
        # Wait and recover
        time.sleep(1.1)
        
        # First success -> HALF_OPEN
        breaker.call(lambda: "success1")
        assert breaker.state == CircuitState.HALF_OPEN
        
        # Second success -> CLOSED
        breaker.call(lambda: "success2")
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0
    
    def test_half_open_reopens_on_failure(self):
        """HALF_OPEN should reopen on failure."""
        breaker = CircuitBreaker(failure_threshold=2, timeout=1)
        
        # Open circuit
        for _ in range(2):
            with pytest.raises(ValueError):
                breaker.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        
        # Wait and attempt recovery
        time.sleep(1.1)
        
        # Fail during recovery
        with pytest.raises(ValueError):
            breaker.call(lambda: (_ for _ in ()).throw(ValueError("still failing")))
        
        # Should be back to OPEN
        assert breaker.state == CircuitState.OPEN
    
    def test_manual_reset(self):
        """Manual reset should close circuit."""
        breaker = CircuitBreaker(failure_threshold=2)
        
        # Open circuit
        for _ in range(2):
            with pytest.raises(ValueError):
                breaker.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        
        assert breaker.state == CircuitState.OPEN
        
        # Manual reset
        breaker.reset()
        
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0
        
        # Should work normally now
        result = breaker.call(lambda: "working")
        assert result == "working"
    
    def test_get_state(self):
        """Should return current state info."""
        breaker = CircuitBreaker(
            failure_threshold=5,
            timeout=60,
            name="test_breaker"
        )
        
        state = breaker.get_state()
        
        assert state["name"] == "test_breaker"
        assert state["state"] == "closed"
        assert state["failure_count"] == 0
        assert state["failure_threshold"] == 5
        assert state["timeout"] == 60
    
    def test_global_circuit_breakers(self):
        """Test global circuit breaker access."""
        polyhaven = get_circuit_breaker("polyhaven")
        assert polyhaven.name == "polyhaven"
        
        hyper3d = get_circuit_breaker("hyper3d")
        assert hyper3d.name == "hyper3d"
        
        sketchfab = get_circuit_breaker("sketchfab")
        assert sketchfab.name == "sketchfab"
    
    def test_unknown_service_raises_error(self):
        """Should raise error for unknown service."""
        with pytest.raises(ValueError) as exc_info:
            get_circuit_breaker("unknown_service")
        
        assert "Unknown service" in str(exc_info.value)
