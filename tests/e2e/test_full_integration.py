import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

# Ensure src is in path
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "src"))

# Mock MCP before imports
import types
from unittest.mock import MagicMock


def _mock_mcp():
    if "mcp" in sys.modules:
        return
    m = types.ModuleType("mcp")
    m.server = types.ModuleType("mcp.server")
    m.server.fastmcp = types.ModuleType("mcp.server.fastmcp")

    class MockFastMCP:
        def __init__(self, *args, **kwargs):
            pass

        def tool(self, *args, **kwargs):
            return lambda f: f

        def resource(self, *args, **kwargs):
            return lambda f: f

        def prompt(self, *args, **kwargs):
            return lambda f: f

    m.server.fastmcp.FastMCP = MockFastMCP
    m.server.fastmcp.Context = MagicMock()
    m.server.fastmcp.Image = MagicMock()
    sys.modules["mcp"] = m
    sys.modules["mcp.server"] = m.server
    sys.modules["mcp.server.fastmcp"] = m.server.fastmcp


_mock_mcp()

from blender_mcp import server


class MockBlenderAddon:
    """Simulates the TCP server that runs inside the Blender addon."""

    def __init__(self, host="localhost", port=9877):
        self.host = host
        self.port = port
        self.running = False
        self.sock = None
        self.responses = {
            "get_scene_info": {"status": "success", "scene": "MockCity"},
            "create_object": {"status": "success", "name": "Cube_1"},
        }

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.listen(1)
        self.running = True
        self.thread = threading.Thread(target=self._run)
        self.thread.daemon = True
        self.thread.start()

    def _run(self):
        while self.running:
            try:
                self.sock.settimeout(1.0)
                conn, addr = self.sock.accept()
                with conn:
                    data = conn.recv(4096)
                    if not data:
                        continue

                    raw_str = data.decode("utf-8")
                    payload = json.loads(raw_str)
                    print(f"DEBUG: Mock Blender received raw: {raw_str}")
                    command_type = payload.get("type")
                    print(f"DEBUG: Mock Blender received type: {command_type}")

                    response = self.responses.get(
                        command_type,
                        {"status": "error", "message": f"Unknown command type: {command_type}"},
                    )
                    # Wrap in the protocol wrapper
                    full_response = {"status": "ok", "result": response}
                    conn.sendall(json.dumps(full_response).encode("utf-8"))
            except TimeoutError:
                continue
            except Exception as e:
                if self.running:
                    print(f"Mock Blender Error: {e}")
                break

    def stop(self):
        self.running = False
        if self.sock:
            self.sock.close()


@pytest.fixture
def mock_blender():
    mock = MockBlenderAddon(port=9877)
    mock.start()
    yield mock
    mock.stop()


def test_mcp_to_blender_bridge(mock_blender, monkeypatch):
    """E2E Test: Verify that server.py can talk to a real TCP server (Mock Blender)."""
    # Force server to use our mock port
    monkeypatch.setenv("BLENDER_PORT", "9877")
    # Reset singleton to pick up new port
    server._blender_connection = None

    # We use server.get_scene_info directly as it's the entry point for the MCP tool
    # Need to mock the Context if it's used, but for a simple call we can pass None
    try:
        # Re-initialize the connection module-level state if necessary
        result_json = server.get_scene_info(ctx=None)

        # If it returned a dict instead of str, it might be tool_error
        if isinstance(result_json, dict):
            result = result_json
        else:
            result = json.loads(result_json)

        if "error" in result:
            print(f"DEBUG: Tool returned error: {result['error']}")

        assert "error" not in result, f"Tool returned unexpected error: {result.get('error')}"
        assert result["status"] == "success"
        assert result["scene"] == "MockCity"
        print("E2E Integration Success: MCP Server -> TCP Bridge -> Mock Blender")
    except Exception as e:
        print(f"DEBUG: Exception during test: {e}")
        pytest.fail(f"E2E Integration Failed: {e}")


if __name__ == "__main__":
    # Manual run
    m = MockBlenderAddon(port=9877)
    m.start()
    print("Mock Blender running on 9877...")
    time.sleep(10)
    m.stop()
