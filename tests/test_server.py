import json
import os
import socket
import sys
import types
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

import pytest


def _add_src_to_path():
    """Ensure the repository's src directory is importable."""
    repo_root = Path(__file__).resolve().parents[1]
    src_path = repo_root / "src"
    if str(src_path) not in os.sys.path:
        os.sys.path.insert(0, str(src_path))


_add_src_to_path()


def _mock_mcp_dependencies():
    """Provide lightweight stand-ins for the mcp package to enable imports."""
    if "mcp" in sys.modules:
        return

    class _DummyFastMCP:
        def __init__(self, *_, **__):
            pass

        def resource(self, *_, **__):
            def decorator(func):
                return func

            return decorator

        def tool(self, *_, **__):
            def decorator(func):
                return func

            return decorator

        def prompt(self, *_, **__):
            def decorator(func):
                return func

            return decorator

    mcp_module = types.ModuleType("mcp")
    mcp_server_module = types.ModuleType("mcp.server")
    mcp_server_fastmcp_module = types.ModuleType("mcp.server.fastmcp")

    mcp_server_fastmcp_module.FastMCP = _DummyFastMCP
    mcp_server_fastmcp_module.Context = MagicMock()
    mcp_server_fastmcp_module.Image = MagicMock()

    mcp_server_module.fastmcp = mcp_server_fastmcp_module
    mcp_module.server = mcp_server_module

    sys.modules["mcp"] = mcp_module
    sys.modules["mcp.server"] = mcp_server_module
    sys.modules["mcp.server.fastmcp"] = mcp_server_fastmcp_module


_mock_mcp_dependencies()

from blender_mcp import server  # noqa: E402  # isort: skip


class _StubSocket:
    def __init__(
        self,
        *,
        recv_chunks=None,
        recv_side_effects=None,
        send_side_effect=None,
        connect_side_effect=None,
    ):
        self.recv_chunks = list(recv_chunks or [])
        self.recv_side_effects = list(recv_side_effects or [])
        self.send_side_effect = send_side_effect
        self.connect_side_effect = connect_side_effect
        self.sent_payloads = []
        self.closed = False
        self.connect_calls = 0
        self.timeout = None

    def settimeout(self, timeout):
        self.timeout = timeout

    def connect(self, address):
        self.connect_calls += 1
        self.address = address
        if self.connect_side_effect:
            raise self.connect_side_effect

    def sendall(self, data):
        if self.send_side_effect:
            raise self.send_side_effect
        self.sent_payloads.append(data)

    def recv(self, _):
        if self.recv_side_effects:
            effect = self.recv_side_effects.pop(0)
            if isinstance(effect, Exception):
                raise effect
            return effect
        if self.recv_chunks:
            return self.recv_chunks.pop(0)
        return b""

    def close(self):
        self.closed = True


@pytest.fixture
def stub_socket(monkeypatch):
    queued_sockets: list[_StubSocket] = []

    def queue_socket(stub: _StubSocket) -> _StubSocket:
        queued_sockets.append(stub)
        return stub

    def fake_socket(*_, **__):
        if not queued_sockets:
            raise AssertionError("No stub sockets queued")
        return queued_sockets.pop(0)

    monkeypatch.setattr(server.socket, "socket", fake_socket)
    return queue_socket


def _stub_connection(**kwargs) -> server.BlenderConnection:
    return server.BlenderConnection(
        host="localhost",
        port=9999,
        timeout=0.01,
        connect_attempts=1,
        command_attempts=kwargs.get("command_attempts", 2),
        backoff_seconds=0,
    )


def test_send_command_recovers_from_partial_response(stub_socket):
    first = stub_socket(
        _StubSocket(
            recv_chunks=[b'{"status": "ok"'],
        )
    )
    second = stub_socket(
        _StubSocket(
            recv_chunks=[b'{"status": "ok", "result": {"value": 1}}'],
        )
    )

    conn = _stub_connection()
    result = conn.send_command("ping", {"sequence": 1})

    assert result == {"value": 1}
    assert first.closed
    assert second.connect_calls == 1


def test_send_command_retries_after_timeout_and_reconnects(stub_socket):
    failing = stub_socket(
        _StubSocket(
            recv_side_effects=[TimeoutError()],
        )
    )
    recovering = stub_socket(
        _StubSocket(
            recv_chunks=[b'{"status": "ok", "result": {"pong": true}}'],
        )
    )

    conn = _stub_connection(command_attempts=1)

    with pytest.raises(Exception) as excinfo:
        conn.send_command("ping", {"sequence": 1})

    assert "Blender did not respond after" in str(excinfo.value)
    assert failing.closed
    assert conn.sock is None

    result = conn.send_command("ping", {"sequence": 2})

    assert result == {"pong": True}
    assert recovering.connect_calls == 1


def test_get_mcp_diagnostics_reports_unreachable_connection(monkeypatch):
    monkeypatch.setattr(
        server,
        "get_blender_connection",
        lambda: (_ for _ in ()).throw(Exception("connection down")),
    )

    result = server.get_mcp_diagnostics(ctx=None)
    payload = json.loads(result)

    assert payload["connection"]["reachable"] is False
    assert "connection down" in payload["connection"]["error"]
    assert "perf_metrics" in payload


def test_get_mcp_diagnostics_reports_scene_probe(monkeypatch):
    mock_blender = MagicMock()
    mock_blender.send_command.return_value = {
        "name": "Scene",
        "object_count": 3,
        "materials_count": 1,
    }
    monkeypatch.setattr(server, "get_blender_connection", lambda: mock_blender)

    result = server.get_mcp_diagnostics(ctx=None)
    payload = json.loads(result)

    assert payload["connection"]["reachable"] is True
    assert payload["scene_probe"]["object_count"] == 3
