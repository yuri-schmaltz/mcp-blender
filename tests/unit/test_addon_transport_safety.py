"""Tests for addon/utils/transport_safety.py.

The addon module is meant to be standalone (it must run inside Blender's
interpreter, which has restricted imports), so we exercise it without any
``bpy`` dependency. We just ``importlib``-load it the same way the addon
does internally.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest


def _load_addon_transport():
    path = (
        Path(__file__).resolve().parent.parent.parent
        / "addon"
        / "utils"
        / "transport_safety.py"
    )
    spec = importlib.util.spec_from_file_location("_blendermcp_ts_under_test", str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ts():
    return _load_addon_transport()


class TestAddonTokenHelpers:
    def test_no_token_allows_everything(self, ts):
        # Ensure no token leaks from the test runner into the addon module.
        os.environ.pop(ts.TOKEN_ENV_VAR, None)
        assert ts.matches_token(None) is True
        assert ts.matches_token({}) is True

    def test_token_required_when_configured(self, ts):
        os.environ[ts.TOKEN_ENV_VAR] = "x" * 32
        try:
            assert ts.matches_token(None) is False
            assert ts.matches_token({}) is False
            assert ts.matches_token({"X-BlenderMCP-Token": "x" * 32}) is True
            assert ts.matches_token({"X-BlenderMCP-Token": "y" * 32}) is False
        finally:
            os.environ.pop(ts.TOKEN_ENV_VAR)

    def test_validate_token(self, ts):
        os.environ[ts.TOKEN_ENV_VAR] = "z" * 32
        try:
            ts.validate_token({"X-BlenderMCP-Token": "z" * 32})  # ok
            with pytest.raises(ts.TokenMismatchError):
                ts.validate_token({})
        finally:
            os.environ.pop(ts.TOKEN_ENV_VAR)


class TestAddonPayloadCap:
    def test_default_cap_4_mib(self, ts):
        # 5 MiB > 4 MiB default, expect rejection.
        with pytest.raises(ts.PayloadTooLargeError):
            ts.enforce_payload_cap(b"x" * (5 * 1024 * 1024))
        # Under default, no exception.
        ts.enforce_payload_cap(b"x" * 1024)


class TestAddonSafeBindHost:
    def test_loopback_ok(self, ts):
        assert ts.safe_bind_host("127.0.0.1") == "127.0.0.1"
        assert ts.safe_bind_host("localhost") == "localhost"

    def test_public_blocked(self, ts):
        os.environ.pop(ts.PUBLIC_BIND_ENV_VAR, None)
        with pytest.raises(PermissionError):
            ts.safe_bind_host("0.0.0.0")
        with pytest.raises(PermissionError):
            ts.safe_bind_host("192.168.1.1")

    def test_public_allowed_with_env(self, ts):
        os.environ[ts.PUBLIC_BIND_ENV_VAR] = "true"
        try:
            assert ts.safe_bind_host("0.0.0.0") == "0.0.0.0"
        finally:
            os.environ.pop(ts.PUBLIC_BIND_ENV_VAR)

    def test_is_loopback(self, ts):
        assert ts.is_loopback_host("127.0.0.1")
        assert ts.is_loopback_host("::1")
        assert ts.is_loopback_host("localhost")
        assert not ts.is_loopback_host("10.0.0.1")
        assert not ts.is_loopback_host("")
