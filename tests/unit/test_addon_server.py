"""Unit tests for addon socket server lifecycle and client handling."""

import json
import sys
from pathlib import Path

# Add repository root to path for addon imports.
repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from addon.server import BlenderMCPServer


class _FakeServerSocket:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _FakeThread:
    def __init__(self, alive=True):
        self._alive = alive
        self.join_calls = []

    def is_alive(self):
        return self._alive

    def join(self, timeout=None):
        self.join_calls.append(timeout)
        self._alive = False


class _FakeClient:
    def __init__(self, recv_events=None):
        self.recv_events = list(recv_events or [])
        self.closed = False
        self.timeout = None
        self.sent_payloads = []

    def settimeout(self, timeout):
        self.timeout = timeout

    def recv(self, _size):
        if not self.recv_events:
            return b""
        event = self.recv_events.pop(0)
        if isinstance(event, Exception):
            raise event
        return event

    def sendall(self, payload):
        self.sent_payloads.append(payload)

    def close(self):
        self.closed = True


class _FakeTimers:
    @staticmethod
    def register(callback, first_interval=0.0):
        _ = first_interval
        callback()
        return None


class _FakeApp:
    timers = _FakeTimers()


class _FakeBpy:
    app = _FakeApp()


def test_stop_cleans_socket_clients_and_threads():
    server = BlenderMCPServer(client_timeout=0.25)
    server.running = True
    server.socket = _FakeServerSocket()
    server.server_thread = _FakeThread(alive=True)

    client_1 = _FakeClient()
    client_2 = _FakeClient()
    worker = _FakeThread(alive=True)

    server._clients.update({client_1, client_2})
    server._client_threads.add(worker)

    server.stop()

    assert server.running is False
    assert server.socket is None
    assert server.server_thread is None
    assert client_1.closed is True
    assert client_2.closed is True
    assert worker.join_calls == [1.0]
    assert not server._clients
    assert not server._client_threads


def test_handle_client_uses_timeout_and_processes_message(monkeypatch):
    monkeypatch.setattr("addon.server.bpy", _FakeBpy())

    command = {"type": "ping", "params": {"x": 1}}
    encoded_command = json.dumps(command).encode("utf-8")
    client = _FakeClient([TimeoutError("tick"), encoded_command, b""])

    server = BlenderMCPServer(client_timeout=0.05)
    server.running = True
    server.command_executor = lambda payload: {"status": "ok", "echo": payload["type"]}

    server._handle_client(client)

    assert client.timeout == 0.05
    assert client.closed is True
    assert len(client.sent_payloads) == 1
    response = json.loads(client.sent_payloads[0].decode("utf-8"))
    assert response["status"] == "ok"
    assert response["echo"] == "ping"


def test_execute_command_without_executor_returns_error():
    server = BlenderMCPServer()
    response = server.execute_command({"type": "ping"})
    assert response["status"] == "error"
    assert "command executor" in response["message"].lower()
