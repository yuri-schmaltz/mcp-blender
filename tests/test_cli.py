import importlib.util
from pathlib import Path

import pytest

from blender_mcp import server


def test_cli_entrypoint_runs_without_blender(monkeypatch):
    calls = []

    class DummyMCP:
        def run(self):
            calls.append("run")

    monkeypatch.setattr(server, "mcp", DummyMCP())
    monkeypatch.setattr(
        server, "get_blender_connection", lambda: pytest.fail("Should not connect")
    )

    spec = importlib.util.spec_from_file_location(
        "blender_mcp_cli", Path(__file__).resolve().parent.parent / "main.py"
    )
    cli_entry = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(cli_entry)

    cli_entry.main()

    assert calls == ["run"]
