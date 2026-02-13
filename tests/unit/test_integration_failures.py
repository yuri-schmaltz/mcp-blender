import pytest

from blender_mcp.server import BlenderConnection, tool_error


def test_connection_refused(monkeypatch):
    """Simula falha de conexão (porta errada)."""
    conn = BlenderConnection(host="localhost", port=9999, connect_attempts=1)
    assert not conn.connect()


def test_command_timeout(monkeypatch):
    """Simula timeout de resposta do servidor."""

    class DummySocket:
        def settimeout(self, t):
            pass

        def sendall(self, data):
            pass

        def recv(self, buf):
            raise TimeoutError()

    conn = BlenderConnection(host="localhost", port=9876)
    conn.sock = DummySocket()
    with pytest.raises(Exception):
        conn.receive_full_response(conn.sock, timeout=0.01)


def test_command_fail(monkeypatch):
    """Simula erro genérico ao enviar comando."""

    class DummySocket:
        def settimeout(self, t):
            pass

        def sendall(self, data):
            raise Exception("fail")

    conn = BlenderConnection(host="localhost", port=9876)
    conn.sock = DummySocket()
    with pytest.raises(Exception, match="did not respond"):
        conn.send_command("fake_command")
