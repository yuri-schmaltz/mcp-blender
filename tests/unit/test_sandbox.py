"""Unit tests for security sandbox module."""

import pytest
import sys
from pathlib import Path

# Add src to path
repo_root = Path(__file__).resolve().parents[2]
src_path = repo_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from blender_mcp.security import (
    execute_code_safe,
    SecurityError,
    TimeoutError,
    RateLimiter,
    create_safe_namespace,
    validate_code,
)


class TestCodeValidation:
    """Test code validation for forbidden patterns."""
    
    def test_allow_safe_code(self):
        """Safe code should pass validation."""
        code = "x = 1 + 2\nprint(x)"
        validate_code(code)  # Should not raise
    
    def test_forbid_os_import(self):
        """OS module imports should be forbidden."""
        code = "import os\nos.system('rm -rf /')"
        with pytest.raises(SecurityError, match="OS module"):
            validate_code(code)
    
    def test_forbid_subprocess(self):
        """Subprocess imports should be forbidden."""
        code = "import subprocess\nsubprocess.call(['ls'])"
        with pytest.raises(SecurityError, match="Subprocess"):
            validate_code(code)
    
    def test_forbid_eval(self):
        """eval() should be forbidden."""
        code = "eval('1+1')"
        with pytest.raises(SecurityError, match="eval"):
            validate_code(code)
    
    def test_forbid_exec(self):
        """exec() should be forbidden."""
        code = "exec('print(1)')"
        with pytest.raises(SecurityError, match="exec"):
            validate_code(code)
    
    def test_forbid_file_operations(self):
        """File operations should be forbidden."""
        code = "open('/etc/passwd', 'r')"
        with pytest.raises(SecurityError, match="File operations"):
            validate_code(code)


class TestSafeNamespace:
    """Test safe namespace creation."""
    
    def test_safe_builtins(self):
        """Safe namespace should contain safe builtins."""
        ns = create_safe_namespace([])
        
        # Should have safe functions
        assert 'print' in ns['__builtins__']
        assert 'len' in ns['__builtins__']
        assert 'range' in ns['__builtins__']
        
        # Should NOT have dangerous functions
        assert 'open' not in ns['__builtins__']
        assert 'eval' not in ns['__builtins__']
        assert 'exec' not in ns['__builtins__']
    
    def test_no_modules_by_default(self):
        """Without allowed modules, namespace shouldn't have imports."""
        ns = create_safe_namespace([])
        assert 'os' not in ns
        assert 'sys' not in ns


class TestRateLimiter:
    """Test rate limiting functionality."""
    
    def test_allows_within_limit(self):
        """Should allow calls within rate limit."""
        limiter = RateLimiter(max_calls=5, window_seconds=60)
        
        for _ in range(5):
            limiter.check_rate_limit()  # Should not raise
    
    def test_blocks_over_limit(self):
        """Should block calls exceeding rate limit."""
        limiter = RateLimiter(max_calls=3, window_seconds=60)
        
        for _ in range(3):
            limiter.check_rate_limit()
        
        with pytest.raises(SecurityError, match="Rate limit"):
            limiter.check_rate_limit()


class TestCodeExecution:
    """Test safe code execution."""
    
    def test_execute_simple_code(self):
        """Should execute simple safe code."""
        code = "result = 2 + 2\nprint(result)"
        result = execute_code_safe(code, check_rate_limit=False)
        
        assert result['executed'] is True
        assert '4' in result['result']
    
    def test_execute_with_math(self):
        """Should execute code with math operations."""
        code = """
x = 10
y = 20
z = x + y * 2
print(f"Result: {z}")
"""
        result = execute_code_safe(code, check_rate_limit=False)
        
        assert result['executed'] is True
        assert '50' in result['result']
    
    def test_block_dangerous_code(self):
        """Should block code with dangerous imports."""
        code = "import os\nprint(os.listdir('/'))"
        
        with pytest.raises(SecurityError):
            execute_code_safe(code, check_rate_limit=False)
    
    def test_block_eval(self):
        """Should block eval usage."""
        code = "result = eval('2+2')"
        
        with pytest.raises(SecurityError):
            execute_code_safe(code, check_rate_limit=False)
    
    def test_error_handling(self):
        """Should catch and report errors in code."""
        code = "x = 1 / 0"  # Division by zero
        result = execute_code_safe(code, check_rate_limit=False)
        
        assert result['executed'] is False
        assert 'error' in result
        assert 'division' in result['error'].lower()
    
    def test_capture_stdout(self):
        """Should capture print statements."""
        code = """
print("Hello")
print("World")
"""
        result = execute_code_safe(code, check_rate_limit=False)
        
        assert 'Hello' in result['result']
        assert 'World' in result['result']
    
    @pytest.mark.skipif(sys.platform == 'win32', reason="Timeout not supported on Windows")
    def test_timeout_long_running(self):
        """Should timeout long-running code."""
        code = "import time\ntime.sleep(10)"
        
        # Note: This will be caught by validate_code before timeout
        with pytest.raises(SecurityError):
            execute_code_safe(code, timeout=1, check_rate_limit=False)
