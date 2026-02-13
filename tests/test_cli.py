import importlib.util
import socket
from pathlib import Path

import pytest

from blender_mcp import cli, server


def test_cli_entrypoint_runs_without_blender(monkeypatch):
    calls = []

    class DummyMCP:
        def run(self):
            calls.append("run")

    monkeypatch.setattr(server, "mcp", DummyMCP())
    monkeypatch.setattr(server, "get_blender_connection", lambda: pytest.fail("Should not connect"))
    monkeypatch.setattr(cli, "configure_logging", lambda **_: None)

    spec = importlib.util.spec_from_file_location(
        "blender_mcp_cli", Path(__file__).resolve().parent.parent / "main.py"
    )
    cli_entry = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(cli_entry)

    cli_entry.main([])

    assert calls == ["run"]


def test_cli_arguments_override_env(monkeypatch):
    monkeypatch.setenv("BLENDER_HOST", "env-host")
    monkeypatch.setenv("BLENDER_PORT", "9999")
    monkeypatch.setenv("BLENDER_MCP_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("BLENDER_MCP_LOG_FORMAT", "%(message)s")
    monkeypatch.setenv("BLENDER_MCP_LOG_HANDLER", "console")

    logging_calls = []

    def fake_configure_logging(*, level=None, log_format=None, handler_type=None):
        logging_calls.append((level, log_format, handler_type))

    monkeypatch.setattr(cli, "configure_logging", fake_configure_logging)

    server_calls = []
    monkeypatch.setattr(
        server, "main", lambda *, host=None, port=None: server_calls.append((host, port))
    )

    cli.main(
        [
            "--host",
            "cli-host",
            "--port",
            "1234",
            "--log-level",
            "debug",
            "--log-format",
            "%(levelname)s:%(message)s",
            "--log-handler",
            "file",
        ]
    )

    assert logging_calls == [("debug", "%(levelname)s:%(message)s", "file")]
    assert server_calls == [("cli-host", 1234)]


def test_cli_print_client_config_exits_without_starting_server(monkeypatch, capsys):
    monkeypatch.setattr(cli, "configure_logging", lambda **_: None)
    monkeypatch.setattr(server, "main", lambda **_: pytest.fail("server.main should not run"))

    cli.main(["--print-client-config", "lm_studio", "--host", "localhost", "--port", "9876"])
    output = capsys.readouterr().out

    assert '"mcpServers"' in output
    assert '"command": "uv"' in output
    assert '"blender-mcp"' in output


def test_cli_doctor_success_exits_without_starting_server(monkeypatch, capsys):
    monkeypatch.setattr(cli, "configure_logging", lambda **_: None)
    monkeypatch.setattr(server, "main", lambda **_: pytest.fail("server.main should not run"))

    class DummyConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(socket, "create_connection", lambda *args, **kwargs: DummyConn())

    with pytest.raises(SystemExit) as exc:
        cli.main(["--doctor", "--host", "localhost", "--port", "9876"])

    output = capsys.readouterr().out
    assert exc.value.code == 0
    assert "basic diagnostics passed" in output


def test_cli_doctor_failure_returns_non_zero(monkeypatch, capsys):
    monkeypatch.setattr(cli, "configure_logging", lambda **_: None)
    monkeypatch.setattr(server, "main", lambda **_: pytest.fail("server.main should not run"))
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("connection refused")),
    )

    with pytest.raises(SystemExit) as exc:
        cli.main(["--doctor", "--host", "localhost", "--port", "9876"])

    output = capsys.readouterr().out
    assert exc.value.code == 1
    assert "cannot connect to Blender addon" in output
