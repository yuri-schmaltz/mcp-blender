"""Tests for the addon-side circuit breaker (addon/utils/circuit_breaker.py)."""

import time

import pytest

from addon.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitState,
    get_all_circuit_states,
    get_circuit_breaker,
    reset_all_circuits,
)


@pytest.fixture(autouse=True)
def _reset_breakers():
    """Reset breaker state before every test for isolation."""
    reset_all_circuits()
    yield
    reset_all_circuits()


# --------------------------------------------------------------------------- #
# Core state machine                                                           #
# --------------------------------------------------------------------------- #


def test_starts_closed():
    breaker = CircuitBreaker(failure_threshold=3, timeout=1, name="t")
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


def test_successful_call_keeps_circuit_closed():
    breaker = CircuitBreaker(failure_threshold=3, timeout=1, name="t")
    for _ in range(10):
        assert breaker.call(lambda: "ok") == "ok"
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


def test_opens_after_threshold_failures():
    breaker = CircuitBreaker(failure_threshold=3, timeout=60, name="t")

    def boom():
        raise RuntimeError("nope")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            breaker.call(boom)

    assert breaker.state == CircuitState.OPEN
    assert breaker.failure_count == 3


def test_open_circuit_rejects_without_calling():
    breaker = CircuitBreaker(failure_threshold=1, timeout=60, name="t")
    with pytest.raises(RuntimeError):
        breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert breaker.state == CircuitState.OPEN

    called = []

    def must_not_run():
        called.append(1)
        return "should not happen"

    with pytest.raises(CircuitBreakerError):
        breaker.call(must_not_run)
    assert called == []


def test_half_open_after_cooldown():
    breaker = CircuitBreaker(failure_threshold=1, timeout=0.05, name="t")
    with pytest.raises(RuntimeError):
        breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert breaker.state == CircuitState.OPEN

    time.sleep(0.06)
    assert breaker.call(lambda: "recovered") == "recovered"
    # First success in HALF_OPEN: still half-open until the second success
    assert breaker.state == CircuitState.HALF_OPEN


def test_half_open_closes_after_two_successes():
    breaker = CircuitBreaker(failure_threshold=1, timeout=0.01, name="t")
    with pytest.raises(RuntimeError):
        breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("x")))
    time.sleep(0.02)
    assert breaker.call(lambda: 1) == 1
    assert breaker.state == CircuitState.HALF_OPEN
    assert breaker.call(lambda: 2) == 2
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


def test_half_open_failure_reopens():
    breaker = CircuitBreaker(failure_threshold=1, timeout=0.01, name="t")
    with pytest.raises(RuntimeError):
        breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("x")))
    time.sleep(0.02)
    with pytest.raises(RuntimeError):
        breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("still bad")))
    assert breaker.state == CircuitState.OPEN


def test_manual_reset_restores_closed():
    breaker = CircuitBreaker(failure_threshold=1, timeout=60, name="t")
    with pytest.raises(RuntimeError):
        breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert breaker.state == CircuitState.OPEN
    breaker.reset()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


def test_get_state_snapshot():
    breaker = CircuitBreaker(failure_threshold=5, timeout=60, name="snap")
    snap = breaker.get_state()
    assert snap == {
        "name": "snap",
        "state": "closed",
        "failure_count": 0,
        "failure_threshold": 5,
        "timeout": 60,
        "time_since_last_failure": None,
    }


# --------------------------------------------------------------------------- #
# Registry / global breakers                                                   #
# --------------------------------------------------------------------------- #


def test_get_known_breaker():
    breaker = get_circuit_breaker("polyhaven")
    assert breaker.name == "polyhaven"
    assert breaker.failure_threshold == 5
    assert breaker.timeout == 60


def test_get_all_registered_breakers():
    services = {"polyhaven", "sketchfab", "ambientcg"}
    breaker = get_circuit_breaker("sketchfab")
    assert breaker.name == "sketchfab"
    # Confirm ambientcg is also registered
    assert get_circuit_breaker("ambientcg").name == "ambientcg"
    assert set(get_all_circuit_states().keys()) == services


def test_unknown_service_raises_value_error():
    with pytest.raises(ValueError, match="Unknown service"):
        get_circuit_breaker("does-not-exist")


def test_get_all_states_reflects_breaker_changes():
    breaker = get_circuit_breaker("polyhaven")
    with pytest.raises(RuntimeError):
        breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("x")))
    states = get_all_circuit_states()
    assert states["polyhaven"]["state"] == "closed"  # only 1 failure, threshold=5
    assert states["polyhaven"]["failure_count"] == 1


def test_reset_all_circuits_returns_to_closed():
    breaker = get_circuit_breaker("sketchfab")
    for _ in range(5):
        with pytest.raises(RuntimeError):
            breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert breaker.state == CircuitState.OPEN
    reset_all_circuits()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0
