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
    # Newer safety policy: non-loopback binds need an explicit opt-in.
    monkeypatch.setenv("BLENDER_MCP_ALLOW_PUBLIC_BIND", "1")

    cli.main([])

    assert calls == ["run"]


def test_cli_arguments_override_env(monkeypatch):
    monkeypatch.setenv("BLENDER_HOST", "env-host")
    monkeypatch.setenv("BLENDER_PORT", "9999")
    monkeypatch.setenv("BLENDER_MCP_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("BLENDER_MCP_LOG_FORMAT", "%(message)s")
    monkeypatch.setenv("BLENDER_MCP_LOG_HANDLER", "console")
    # Default policy: refuse non-loopback hosts. The explicit
    # ``--allow-public-bind`` flag below opts in for this test.
    monkeypatch.delenv("BLENDER_MCP_ALLOW_PUBLIC_BIND", raising=False)

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
            "--allow-public-bind",
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


def test_cli_refuses_non_loopback_without_opt_in(monkeypatch, capsys):
    """Newer safety policy: ``--host 0.0.0.0`` needs ``--allow-public-bind``."""
    monkeypatch.setattr(cli, "configure_logging", lambda **_: None)
    monkeypatch.setattr(server, "main", lambda **_: pytest.fail("server.main should not run"))

    with pytest.raises(SystemExit) as exc:
        cli.main(["--host", "0.0.0.0", "--port", "9876"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "refusing to bind" in err


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
    assert "OK: basic diagnostics passed" in output


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
    # The new doctor uses the section-prefixed form like "[FAIL]  tcp-connect: ...".
    assert ("cannot connect" in output) or ("tcp-connect" in output)
