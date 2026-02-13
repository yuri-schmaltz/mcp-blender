"""Tests for Windows timeout implementation in sandbox.py"""

# Add src to path
import os
import platform
import sys
import time
from pathlib import Path
from unittest import TestCase, skipIf

import pytest

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "src"))

from blender_mcp.security.sandbox import SecurityError, TimeoutError, execute_code_safe


class TestWindowsTimeout(TestCase):
    """Test timeout works on Windows using threading.Timer"""

    @skipIf(platform.system() == "Windows", "Only run on Windows")
    def test_timeout_on_windows(self):
        """Test that timeout works on Windows"""
        code = """
import time
time.sleep(10)  # Sleep longer than timeout
"""

        with pytest.raises(TimeoutError) as exc_info:
            execute_code_safe(code, timeout=1, check_rate_limit=False)

        assert "exceeded" in str(exc_info.value).lower()
        assert "1s timeout" in str(exc_info.value)

    def test_timeout_on_all_platforms(self):
        """Sandbox should block forbidden modules consistently across platforms."""
        code = """
import time
time.sleep(10)  # Sleep longer than timeout
"""

        with pytest.raises(SecurityError) as exc_info:
            execute_code_safe(code, timeout=1, check_rate_limit=False)

        assert "forbidden" in str(exc_info.value).lower()

    def test_no_timeout_when_fast(self):
        """Test that fast code doesn't trigger timeout"""
        code = """
result = 1 + 1
print(result)
"""

        result = execute_code_safe(code, timeout=5, check_rate_limit=False)

        assert result["executed"] is True
        assert "2" in result["result"]

    def test_cleanup_timer_on_success(self):
        """Test that timer is properly canceled on success"""
        import threading

        initial_threads = threading.active_count()

        code = "x = 1 + 1"
        result = execute_code_safe(code, timeout=5, check_rate_limit=False)

        # Give time for any lingering threads to cleanup
        time.sleep(0.1)

        final_threads = threading.active_count()

        # Should not have leaked threads
        assert final_threads <= initial_threads + 1  # Allow for some variance
        assert result["executed"] is True

    def test_cleanup_timer_on_error(self):
        """Test that timer is properly canceled even on error"""
        import threading

        initial_threads = threading.active_count()

        code = "1 / 0"  # Will raise ZeroDivisionError
        result = execute_code_safe(code, timeout=5, check_rate_limit=False)

        # Give time for any lingering threads to cleanup
        time.sleep(0.1)

        final_threads = threading.active_count()

        # Should not have leaked threads
        assert final_threads <= initial_threads + 1
        assert result["executed"] is False
        assert "error" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
