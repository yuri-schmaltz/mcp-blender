"""Security utilities for sandboxed code execution in Blender.

This module provê execução segura de código com restrição de imports, timeouts,
rate limiting e logging de violações.

Checklist de segurança (mínimo):
 - Validação de entrada rigorosa
 - Limite de tempo de execução (timeout)
 - Rate limiting por janela de tempo
 - Logging de toda violação (SecurityError, TimeoutError)
 - Não permitir imports perigosos (os, sys, subprocess, etc)
 - Testes de fuzzing e revisão periódica
"""

import logging
import signal
from collections import deque
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """Raised when sandboxed code violates security policies."""

    pass


class TimeoutError(Exception):
    """Raised when code execution exceeds timeout limit."""

    pass


class RateLimiter:
    """Rate limit code executions to prevent abuse."""

    def __init__(self, max_calls: int = 10, window_seconds: int = 60):
        """
        Args:
            max_calls: Maximum number of calls allowed in the time window
            window_seconds: Time window in seconds
        """
        self.max_calls = max_calls
        self.window = timedelta(seconds=window_seconds)
        self.calls: deque = deque()

    def check_rate_limit(self) -> None:
        """Check if rate limit is exceeded. Loga violações."""
        now = datetime.now()

        # Remove old calls outside the window
        while self.calls and now - self.calls[0] > self.window:
            self.calls.popleft()

        if len(self.calls) >= self.max_calls:
            logger.warning(
                f"Rate limit exceeded: max {self.max_calls} calls per {self.window.seconds}s"
            )
            raise SecurityError(
                f"Rate limit exceeded: max {self.max_calls} calls per " f"{self.window.seconds}s"
            )

        self.calls.append(now)


# Global rate limiter instance
_rate_limiter = RateLimiter(max_calls=10, window_seconds=60)


def create_safe_namespace(allowed_modules: list[str] | None = None) -> dict[str, Any]:
    """Create a restricted namespace for code execution.

    Args:
        allowed_modules: List of module names allowed for import.
                        Defaults to ['bpy', 'mathutils']

    Returns:
        Dictionary with safe builtins and allowed modules
    """
    if allowed_modules is None:
        allowed_modules = ["bpy", "mathutils"]

    # Safe builtins - remove dangerous functions
    safe_builtins = {
        "abs": abs,
        "all": all,
        "any": any,
        "bool": bool,
        "dict": dict,
        "enumerate": enumerate,
        "filter": filter,
        "float": float,
        "int": int,
        "len": len,
        "list": list,
        "map": map,
        "max": max,
        "min": min,
        "print": print,
        "range": range,
        "round": round,
        "sorted": sorted,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        "zip": zip,
        # Math functions
        "pow": pow,
        # Type checking
        "isinstance": isinstance,
        "type": type,
    }

    namespace = {
        "__builtins__": safe_builtins,
        "__name__": "__main__",
        "__doc__": None,
    }

    # Import allowed modules
    for module_name in allowed_modules:
        try:
            if module_name == "bpy":
                import bpy

                namespace["bpy"] = bpy
            elif module_name == "mathutils":
                import mathutils

                namespace["mathutils"] = mathutils
        except ImportError:
            logger.warning(f"Could not import allowed module: {module_name}")

    return namespace


def validate_code(code: str) -> None:
    """Validate code for forbidden patterns.

    Args:
        code: Python code string to validate

    Raises:
        SecurityError: If code contains forbidden patterns
    """
    forbidden_patterns = [
        ("import os", "OS module access forbidden"),
        ("import sys", "System module access forbidden"),
        ("import subprocess", "Subprocess execution forbidden"),
        ("import socket", "Socket operations forbidden"),
        ("import requests", "HTTP requests forbidden in sandboxed code"),
        ("import time", "Time module access forbidden"),
        ("eval(", "eval() is forbidden"),
        ("exec(", "exec() is forbidden"),
        ("compile(", "compile() is forbidden"),
        ("__import__", "__import__ is forbidden"),
        ("open(", "File operations forbidden"),
        ("file(", "File operations forbidden"),
    ]

    code_lower = code.lower()
    for pattern, message in forbidden_patterns:
        if pattern.lower() in code_lower:
            raise SecurityError(f"Forbidden operation: {message}")


def execute_code_safe(
    code: str,
    timeout: int = 5,
    allowed_modules: list[str] | None = None,
    check_rate_limit: bool = True,
) -> dict[str, Any]:
    """Execute Python code in a sandboxed environment.

    Args:
        code: Python code to execute
        timeout: Maximum execution time in seconds
        allowed_modules: List of modules allowed for import
        check_rate_limit: Whether to enforce rate limiting

    Returns:
        Dictionary with:
            - executed (bool): Whether execution was successful
            - result (str): Captured stdout output
            - error (str, optional): Error message if execution failed

    Raises:
        SecurityError: If code violates security policies or rate limit
        TimeoutError: If execution exceeds timeout
    """
    # Check rate limit
    if check_rate_limit:
        _rate_limiter.check_rate_limit()

    # Validate code for forbidden patterns
    validate_code(code)

    # Create safe namespace
    namespace = create_safe_namespace(allowed_modules)

    # Capture stdout
    import io
    from contextlib import redirect_stdout

    output = io.StringIO()

    # Detect platform
    import platform

    use_signal_timeout = platform.system() != "Windows"

    # Setup timeout mechanism
    timer = None
    timed_out = [False]  # Use list to allow modification in nested function

    def timeout_handler(*args):
        timed_out[0] = True
        raise TimeoutError(f"Code execution exceeded {timeout}s timeout")

    try:
        if use_signal_timeout:
            # Unix/Linux: use signal-based timeout
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout)
        else:
            # Windows: use threading.Timer
            import threading

            timer = threading.Timer(timeout, timeout_handler)
            timer.daemon = True
            timer.start()

        with redirect_stdout(output):
            exec(code, namespace)

        # Cancel timeout
        if use_signal_timeout:
            signal.alarm(0)  # Cancel alarm
        elif timer:
            timer.cancel()

        return {"executed": True, "result": output.getvalue()}

    except TimeoutError as e:
        logger.error(f"Code execution timeout: {str(e)}")
        raise

    except SecurityError as e:
        logger.error(f"Security violation: {str(e)}")
        raise

    except Exception as e:
        logger.error(f"Code execution error: {str(e)}", exc_info=True)
        return {"executed": False, "result": output.getvalue(), "error": str(e)}

    finally:
        # Ensure cleanup
        if use_signal_timeout:
            signal.alarm(0)  # Ensure alarm is cancelled
        elif timer:
            timer.cancel()
