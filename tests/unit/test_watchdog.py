import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add repository root to path for addon imports
repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import pytest

from blender_mcp.server import BlenderWatchdog


class DummyConnection:
    def __init__(self, socket_alive=True, main_thread_alive=True, pid=12345, is_rendering=False):
        self.status = {
            "socket_alive": socket_alive,
            "main_thread_alive": main_thread_alive,
            "pid": pid,
            "is_rendering": is_rendering,
            "error": None,
        }

    def ping_status(self):
        return self.status


def test_watchdog_unresponsive_kills_and_restarts():
    # 1. Setup responsive dummy connection (both socket and main thread are alive)
    conn = DummyConnection(socket_alive=True, main_thread_alive=True, pid=12345)

    # We configure watchdog to check every 0.05s and trigger after 0.15s of unresponsiveness
    watchdog = BlenderWatchdog(conn, check_interval=0.05, max_unresponsive_seconds=0.15)

    with patch("os.kill") as mock_kill, patch("subprocess.Popen") as mock_popen:
        watchdog.start_watchdog(run_command_args=["blender", "--background"])

        # Give it a moment to run a few loops while responsive
        time.sleep(0.1)
        assert mock_kill.call_count == 0
        assert mock_popen.call_count == 0

        # Now make the connection unresponsive (socket is alive, but main thread is frozen)
        conn.status["main_thread_alive"] = False

        # Wait for the watchdog to detect and trigger recovery
        time.sleep(0.3)

        # Stop the watchdog
        watchdog.stop_watchdog()

        # Assertions: kill and restart should be triggered!
        assert mock_kill.call_count > 0
        mock_kill.assert_called_with(12345, signal.SIGKILL)

        assert mock_popen.call_count > 0
        mock_popen.assert_called_with(
            ["blender", "--background"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


def test_watchdog_is_rendering_does_not_kill():
    # If the main thread is busy because of a render, the watchdog should NOT trigger a kill/restart
    conn = DummyConnection(socket_alive=True, main_thread_alive=False, pid=12345, is_rendering=True)
    watchdog = BlenderWatchdog(conn, check_interval=0.05, max_unresponsive_seconds=0.15)

    with patch("os.kill") as mock_kill, patch("subprocess.Popen") as mock_popen:
        watchdog.start_watchdog(run_command_args=["blender"])
        time.sleep(0.3)
        watchdog.stop_watchdog()

        # Since it is rendering, no kill/restart should occur
        assert mock_kill.call_count == 0
        assert mock_popen.call_count == 0
