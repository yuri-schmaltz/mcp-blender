from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from pathlib import Path

import pytest

BLENDER_EXE = Path(os.getenv("BLENDER_EXE", r"C:\Blender\blender.exe"))
BOOTSTRAP_SCRIPT = Path(__file__).resolve().parent / "e2e" / "blender_smoke_bootstrap.py"


def _reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _recv_json(sock: socket.socket, timeout: float = 5.0) -> dict:
    sock.settimeout(timeout)
    chunks: list[bytes] = []
    while True:
        chunk = sock.recv(8192)
        if not chunk:
            break
        chunks.append(chunk)
        try:
            return json.loads(b"".join(chunks).decode("utf-8"))
        except json.JSONDecodeError:
            continue
    raise RuntimeError("No complete JSON response received from Blender addon")


def _send_command(port: int, command_type: str, params: dict | None = None) -> dict:
    payload = {"type": command_type, "params": params or {}}
    with socket.create_connection(("127.0.0.1", port), timeout=5.0) as sock:
        sock.sendall(json.dumps(payload).encode("utf-8"))
        return _recv_json(sock)


def _wait_until_ready(proc: subprocess.Popen[str], timeout_seconds: float = 40.0) -> None:
    deadline = time.time() + timeout_seconds
    if proc.stdout is None:
        raise RuntimeError("Blender smoke process has no stdout")

    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                break
            continue

        if "BLENDERMCP_SMOKE_READY" in line:
            return
        if "BLENDERMCP_SMOKE_ERROR" in line:
            raise RuntimeError(line.strip())

    raise TimeoutError("Timed out waiting for Blender MCP smoke server to start")


@pytest.mark.e2e
def test_blender_addon_server_start_stop():
    if not BLENDER_EXE.exists():
        pytest.skip(f"Blender executable not found at {BLENDER_EXE}")

    port = _reserve_port()
    env = os.environ.copy()
    env["BLENDER_MCP_SMOKE_PORT"] = str(port)

    proc = subprocess.Popen(
        [
            str(BLENDER_EXE),
            "--factory-startup",
            "--python",
            str(BOOTSTRAP_SCRIPT),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
    )

    try:
        _wait_until_ready(proc)

        scene_response = _send_command(port, "get_scene_info")
        assert scene_response["status"] == "success"
        assert isinstance(scene_response.get("result"), dict)

        exec_response = _send_command(
            port,
            "execute_code",
            {"code": "print('smoke_ok')"},
        )
        assert exec_response["status"] == "success"
        assert exec_response["result"]["executed"] is True
        assert "smoke_ok" in exec_response["result"]["result"]
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
