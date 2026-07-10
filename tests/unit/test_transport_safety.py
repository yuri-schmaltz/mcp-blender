"""Tests for src/blender_mcp/security/transport.py."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest


def _import_transport():
    """Import the shared transport helpers (skip if not on PYTHONPATH)."""
    src_path = Path(__file__).resolve().parent.parent.parent / "src"
    sys.path.insert(0, str(src_path))
    return importlib.import_module("blender_mcp.security.transport")


class TestSafeBindHost:
    def setup_method(self):
        self.t = _import_transport()
        # Make sure the env var is cleared for these tests.
        self._saved = os.environ.pop(self.t.PUBLIC_BIND_ENV_VAR, None)

    def teardown_method(self):
        if self._saved is not None:
            os.environ[self.t.PUBLIC_BIND_ENV_VAR] = self._saved
        else:
            os.environ.pop(self.t.PUBLIC_BIND_ENV_VAR, None)

    def test_loopback_hosts_pass(self):
        for host in ("localhost", "127.0.0.1", "::1"):
            assert self.t.safe_bind_host(host) == host

    def test_wildcard_blocked_by_default(self):
        with pytest.raises(PermissionError):
            self.t.safe_bind_host("0.0.0.0")
        with pytest.raises(PermissionError):
            self.t.safe_bind_host("::")

    def test_wildcard_allowed_with_env(self):
        os.environ[self.t.PUBLIC_BIND_ENV_VAR] = "1"
        assert self.t.safe_bind_host("0.0.0.0") == "0.0.0.0"

    def test_non_loopback_ip_blocked_by_default(self):
        with pytest.raises(PermissionError):
            self.t.safe_bind_host("10.0.0.5")

    def test_non_loopback_ip_allowed_with_explicit_flag(self):
        # Explicit override bypasses the env var.
        assert self.t.safe_bind_host("10.0.0.5", allow_public=True) == "10.0.0.5"

    def test_empty_host_rejected(self):
        with pytest.raises(PermissionError):
            self.t.safe_bind_host("")


class TestTokenHelpers:
    def setup_method(self):
        self.t = _import_transport()
        self._saved = os.environ.pop(self.t.TOKEN_ENV_VAR, None)

    def teardown_method(self):
        if self._saved is not None:
            os.environ[self.t.TOKEN_ENV_VAR] = self._saved
        else:
            os.environ.pop(self.t.TOKEN_ENV_VAR, None)

    def test_no_token_means_open_seat(self):
        assert self.t.matches_token(None) is True
        assert self.t.matches_token({}) is True

    def test_token_required_when_configured(self):
        os.environ[self.t.TOKEN_ENV_VAR] = "secret"
        assert self.t.matches_token(None) is False
        assert self.t.matches_token({}) is False
        assert self.t.matches_token({"some": "header"}) is False

    def test_token_matches_case_insensitive(self):
        os.environ[self.t.TOKEN_ENV_VAR] = "secret"
        assert (
            self.t.matches_token({"X-BlenderMCP-Token": "secret"}) is True
        )
        assert (
            self.t.matches_token({"x-blendermcp-token": "secret"}) is True
        )
        assert (
            self.t.matches_token({"X-BlenderMCP-Token": "wrong"}) is False
        )

    def test_validate_token_raises_on_mismatch(self):
        os.environ[self.t.TOKEN_ENV_VAR] = "secret"
        self.t.validate_token({"X-BlenderMCP-Token": "secret"})  # no raise
        with pytest.raises(self.t.TokenMismatchError):
            self.t.validate_token({})


class TestPayloadCap:
    def setup_method(self):
        self.t = _import_transport()
        self._saved = os.environ.pop(self.t.MAX_PAYLOAD_ENV_VAR, None)

    def teardown_method(self):
        if self._saved is not None:
            os.environ[self.t.MAX_PAYLOAD_ENV_VAR] = self._saved
        else:
            os.environ.pop(self.t.MAX_PAYLOAD_ENV_VAR, None)

    def test_default_limit_applies(self):
        # Default is 4 MiB; 5 MiB should blow.
        big = b"x" * (5 * 1024 * 1024)
        with pytest.raises(self.t.PayloadTooLargeError):
            self.t.enforce_payload_cap(big)

    def test_within_default_limit_passes(self):
        small = b"x" * 1024
        # Should not raise.
        self.t.enforce_payload_cap(small)

    def test_string_payload_uses_utf8_size(self):
        # 1024 ascii chars = 1024 bytes, well below default.
        self.t.enforce_payload_cap("x" * 1024)
        # And huge string should blow.
        with pytest.raises(self.t.PayloadTooLargeError):
            self.t.enforce_payload_cap("x" * (5 * 1024 * 1024))

    def test_custom_limit_respected(self):
        os.environ[self.t.MAX_PAYLOAD_ENV_VAR] = "100"
        with pytest.raises(self.t.PayloadTooLargeError):
            self.t.enforce_payload_cap(b"x" * 200)
        # 100 bytes exactly is still over because the check is strict-greater.
        self.t.enforce_payload_cap(b"x" * 99)

    def test_invalid_cap_falls_back_to_default(self):
        os.environ[self.t.MAX_PAYLOAD_ENV_VAR] = "not-a-number"
        # 5 MiB blows against the default.
        with pytest.raises(self.t.PayloadTooLargeError):
            self.t.enforce_payload_cap(b"x" * (5 * 1024 * 1024))
