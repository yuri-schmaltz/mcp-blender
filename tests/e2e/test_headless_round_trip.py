"""End-to-end test suite that runs Blender in --background mode and
exercises the transport hardening (token + payload cap + bind guard)
through the real socket server.

These tests are skipped automatically when Blender is not on PATH
(via ``BLENDER_EXE`` env var).

They take a few seconds each because they spawn a Blender process; mark
the file as ``e2e`` so the standard ``-m 'not e2e'`` skip works.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS = REPO_ROOT / "tests" / "e2e" / "headless_runner.py"
SMOKE = REPO_ROOT / "tests" / "e2e" / "smoke_security.py"

DEFAULT_BLENDER = (
    "/opt/blender-5.1.2-linux-x64/blender"
)
BLENDER_EXE = Path(os.environ.get("BLENDER_EXE", DEFAULT_BLENDER))


def _blender_available() -> bool:
    if not BLENDER_EXE.exists():
        return False
    return shutil.which(str(BLENDER_EXE)) is not None or BLENDER_EXE.is_file()


pytestmark = pytest.mark.skipif(
    not _blender_available(),
    reason=f"Blender executable not found at {BLENDER_EXE}",
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _spawn_blender(port: int, token: str | None, payload_cap: int | None) -> subprocess.Popen:
    env = os.environ.copy()
    env["BLENDER_MCP_HARNESS_PORT"] = str(port)
    env["BLENDER_MCP_HARNESS_KEEPALIVE"] = "60"
    env["MCP_REPO_ROOT"] = str(REPO_ROOT)
    if token is not None:
        env["BLENDER_MCP_TOKEN"] = token
    if payload_cap is not None:
        env["BLENDER_MCP_MAX_PAYLOAD_BYTES"] = str(payload_cap)

    return subprocess.Popen(
        [
            str(BLENDER_EXE),
            "--factory-startup",
            "--background",
            "--python",
            str(HARNESS),
            "--python-exit-code",
            "0",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )


def _wait_ready(proc: subprocess.Popen, timeout: float = 60.0) -> str:
    """Wait for BLENDERMCP_SMOKE_READY in the proc's stdout."""
    deadline = time.time() + timeout
    lines: list[str] = []
    last_poll_log = time.time()
    while time.time() < deadline:
        if proc.stdout is None:
            raise RuntimeError("blender subprocess has no stdout")
        line = proc.stdout.readline()
        if line:
            lines.append(line)
            if "BLENDERMCP_SMOKE_READY" in line:
                return "".join(lines)
        else:
            if proc.poll() is not None:
                tail = proc.stdout.read()
                raise RuntimeError(
                    f"blender exited early (rc={proc.returncode}). log:\n"
                    + "".join(lines)
                    + tail
                )
            # Periodic poll log to help debug hangs without printing
            # every iteration.
            now = time.time()
            if now - last_poll_log > 5:
                last_poll_log = now
        time.sleep(0.1)
    raise TimeoutError("blender never printed SMOKE_READY; tail:\n" + "".join(lines))


def _terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _run_smoke(port: int, token: str | None, payload_cap: int | None):
    env = os.environ.copy()
    env["BLENDER_MCP_HARNESS_PORT"] = str(port)
    if token is not None:
        env["BLENDER_MCP_TOKEN"] = token
    if payload_cap is not None:
        env["BLENDER_MCP_MAX_PAYLOAD_BYTES"] = str(payload_cap)
    result = subprocess.run(
        [sys.executable, str(SMOKE)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result


@pytest.mark.e2e
def test_round_trip_no_token_no_cap():
    """Without token or low cap, baseline commands work and a multi-MiB
    payload is still rejected by the default 4 MiB cap (here exercised
    via a separately-spawned high-cap test below)."""
    port = _free_port()
    proc = _spawn_blender(port=port, token=None, payload_cap="2048")
    try:
        _wait_ready(proc)
        result = _run_smoke(port, token=None, payload_cap="2048")
        assert result.returncode == 0, (
            f"smoke_security failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert "PASS  ping_thread" in result.stdout
        assert "PASS  execute_code" in result.stdout
        assert "PASS  no_token_open_seat" in result.stdout
        assert "PASS  payload_cap_2mb" in result.stdout
    finally:
        _terminate(proc)


@pytest.mark.e2e
def test_round_trip_token_enforced_and_match():
    """With ``BLENDER_MCP_TOKEN`` set in BOTH the Blender process and the
    smoke runner, wrong tokens are refused with ``token_mismatch`` and
    the matching token passes."""
    port = _free_port()
    token = "test-token-roundtrip-1234567890"
    proc = _spawn_blender(port=port, token=token, payload_cap="2048")
    try:
        _wait_ready(proc)
        result = _run_smoke(port, token=token, payload_cap="2048")
        assert result.returncode == 0, (
            f"smoke_security failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert "PASS  wrong_token_rejected" in result.stdout
        assert "PASS  right_token_accepted" in result.stdout
        # The cap check is shared across scenarios.
        assert "PASS  payload_cap_2mb" in result.stdout
    finally:
        _terminate(proc)


@pytest.mark.e2e
def test_round_trip_payload_cap_default_4mib():
    """With the cap left at default (4 MiB), a 5 MiB payload must be
    rejected -- this proves the bundled default limit kicks in even
    when the env override is absent."""
    port = _free_port()
    proc = _spawn_blender(port=port, token=None, payload_cap=None)
    try:
        _wait_ready(proc)
        # Run a tiny bespoke client that sends 5 MiB.
        # We avoid modifying smoke_security.py because that file uses
        # an 8 KiB fixture for the low-cap test.
        env = os.environ.copy()
        env["BLENDER_MCP_HARNESS_PORT"] = str(port)
        client = REPO_ROOT / "tests" / "e2e" / "_5mb_client.py"
        client.write_text(
            "import json, os, socket\n"
            f"PORT = {port}\n"
            "huge = {'type': 'ping_thread', 'params': {}, 'headers': {'x': 'A' * (5 * 1024 * 1024)}}\n"
            "s = socket.create_connection(('127.0.0.1', PORT), timeout=20)\n"
            "s.sendall(json.dumps(huge).encode('utf-8'))\n"
            "chunks = []\n"
            "s.settimeout(8)\n"
            "while True:\n"
            "    try:\n"
            "        c = s.recv(65536)\n"
            "    except socket.timeout:\n"
            "        break\n"
            "    if not c:\n"
            "        break\n"
            "    chunks.append(c)\n"
            "body = b''.join(chunks).decode('utf-8', 'replace')\n"
            "print('CAP_REJECTED' if 'payload_too_large' in body else 'CAP_BYPASS', body[:200])\n"
        )
        result = subprocess.run(
            [sys.executable, str(client)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert "CAP_REJECTED" in result.stdout, (
            f"expected CAP_REJECTED, got:\n{result.stdout}\n{result.stderr}"
        )
    finally:
        _terminate(proc)
        # Cleanup tmp client so it doesn't pollute the repo.
        try:
            (REPO_ROOT / "tests" / "e2e" / "_5mb_client.py").unlink()
        except OSError:
            pass
