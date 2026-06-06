# blender_mcp_server.py
import errno
import json
import logging
import os
import socket
import tempfile
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context, FastMCP, Image

from blender_mcp.perf_metrics import perf_metrics

from .logging_config import configure_logging


def tool_error(
    message: str, *, code: str = "runtime_error", data: dict[str, Any] | None = None
) -> Any:
    details = f" [details: {data}]" if data else ""
    raise Exception(f"{message} (code: {code}){details}")


logger = logging.getLogger("BlenderMCPServer")

# Default configuration
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 9876
DEFAULT_SOCKET_TIMEOUT = 15.0
DEFAULT_CONNECT_ATTEMPTS = 3
DEFAULT_COMMAND_ATTEMPTS = 3
DEFAULT_RETRY_BACKOFF = 1.0


class IncompleteResponseError(Exception):
    """Raised when Blender closes or times out before sending a full JSON response."""


def _is_transient_socket_error(error: Exception) -> bool:
    transient_errors = (
        TimeoutError,
        BrokenPipeError,
        ConnectionAbortedError,
        ConnectionResetError,
    )

    if isinstance(error, transient_errors):
        return True

    if isinstance(error, OSError) and getattr(error, "errno", None) in {
        errno.ECONNREFUSED,
        errno.ECONNRESET,
        errno.ETIMEDOUT,
    }:
        return True

    return False


@dataclass
class BlenderConnection:
    host: str
    port: int
    timeout: float = DEFAULT_SOCKET_TIMEOUT
    connect_attempts: int = DEFAULT_CONNECT_ATTEMPTS
    command_attempts: int = DEFAULT_COMMAND_ATTEMPTS
    backoff_seconds: float = DEFAULT_RETRY_BACKOFF
    sock: socket.socket | None = None

    def _sleep_with_backoff(self, attempt: int) -> None:
        time.sleep(self.backoff_seconds * attempt)

    def connect(self) -> bool:
        """Connect to the Blender addon socket server with retries"""
        if self.sock:
            return True

        for attempt in range(1, self.connect_attempts + 1):
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(self.timeout)
                self.sock.connect((self.host, self.port))
                logger.info(
                    "Connected to Blender at %s:%s on attempt %s/%s",
                    self.host,
                    self.port,
                    attempt,
                    self.connect_attempts,
                )
                return True
            except Exception as e:
                logger.warning(
                    "Failed to connect to Blender at %s:%s on attempt %s/%s: %s",
                    self.host,
                    self.port,
                    attempt,
                    self.connect_attempts,
                    str(e),
                )
                self.sock = None

                if attempt >= self.connect_attempts or not _is_transient_socket_error(e):
                    logger.error("Giving up on Blender connection after %s attempts", attempt)
                    return False

                self._sleep_with_backoff(attempt)

    def disconnect(self):
        """Disconnect from the Blender addon"""
        if self.sock:
            try:
                self.sock.close()
            except Exception as e:
                logger.error(f"Error disconnecting from Blender: {str(e)}")
            finally:
                self.sock = None

    def receive_full_response(self, sock, buffer_size=8192, timeout: float | None = None):
        """Receive the complete response, potentially in multiple chunks"""
        chunks = []
        sock.settimeout(timeout or self.timeout)

        try:
            while True:
                try:
                    chunk = sock.recv(buffer_size)
                    if not chunk:
                        # If we get an empty chunk, the connection might be closed
                        if not chunks:  # If we haven't received anything yet, this is an error
                            raise Exception("Connection closed before receiving any data")
                        break

                    chunks.append(chunk)

                    # Check if we've received a complete JSON object
                    try:
                        data = b"".join(chunks)
                        json.loads(data.decode("utf-8"))
                        # If we get here, it parsed successfully
                        logger.info(f"Received complete response ({len(data)} bytes)")
                        return data
                    except json.JSONDecodeError:
                        # Incomplete JSON, continue receiving
                        continue
                except TimeoutError as e:
                    logger.warning("Socket timeout during chunked receive")
                    raise IncompleteResponseError("Timed out waiting for Blender response") from e
                except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
                    logger.error(f"Socket connection error during receive: {str(e)}")
                    raise
        except IncompleteResponseError:
            raise
        except Exception as e:
            logger.error(f"Error during receive: {str(e)}")
            raise

        # If we get here, we either timed out or broke out of the loop
        # Try to use what we have
        if chunks:
            data = b"".join(chunks)
            logger.info(f"Returning data after receive completion ({len(data)} bytes)")
            try:
                json.loads(data.decode("utf-8"))
                return data
            except json.JSONDecodeError as e:
                raise IncompleteResponseError("Incomplete JSON response received") from e

        raise IncompleteResponseError("No data received")

    def send_command(self, command_type: str, params: dict[str, Any] = None) -> dict[str, Any]:
        """Send a command to Blender and return the response"""
        command = {"type": command_type, "params": params or {}}

        last_error: Exception | None = None

        for attempt in range(1, self.command_attempts + 1):
            if not self.sock and not self.connect():
                last_error = ConnectionError("Not connected to Blender")
                break

            try:
                logger.info(
                    "Sending command '%s' (attempt %s/%s) with params: %s",
                    command_type,
                    attempt,
                    self.command_attempts,
                    params,
                )

                self.sock.settimeout(self.timeout)
                self.sock.sendall(json.dumps(command).encode("utf-8"))
                logger.info("Command sent, waiting for response...")

                response_data = self.receive_full_response(self.sock, timeout=self.timeout)
                logger.info("Received %s bytes of data", len(response_data))

                response = json.loads(response_data.decode("utf-8"))
                logger.info("Response parsed, status: %s", response.get("status", "unknown"))

                if response.get("status") == "error":
                    logger.error("Blender error: %s", response.get("message"))
                    raise Exception(response.get("message", "Unknown error from Blender"))

                return response.get("result", {})
            except IncompleteResponseError as e:
                last_error = e
                logger.warning(
                    "Received incomplete response from Blender (attempt %s/%s): %s",
                    attempt,
                    self.command_attempts,
                    str(e),
                )
            except (
                ConnectionError,
                BrokenPipeError,
                ConnectionResetError,
                ConnectionAbortedError,
                TimeoutError,
            ) as e:
                last_error = e
                logger.warning(
                    "Transient socket issue while communicating with Blender (attempt %s/%s): %s",
                    attempt,
                    self.command_attempts,
                    str(e),
                )
            except json.JSONDecodeError as e:
                last_error = e
                logger.error("Invalid JSON response from Blender: %s", str(e))
                if "response_data" in locals() and response_data:
                    logger.error("Raw response (first 200 bytes): %s", response_data[:200])
                break
            except Exception as e:
                last_error = e
                logger.error("Error communicating with Blender: %s", str(e))
                break
            finally:
                if last_error:
                    self.disconnect()

            if attempt < self.command_attempts:
                self._sleep_with_backoff(attempt)

        assert last_error is not None
        raise Exception(
            f"Blender did not respond after {self.command_attempts} attempts: {last_error}"
        )

    def ping_status(self) -> dict[str, Any]:
        """
        Sends ping_thread and ping_main commands to Blender to determine connection and thread health.
        Returns a status dict:
          - "socket_alive": bool
          - "main_thread_alive": bool
          - "pid": int | None
          - "is_rendering": bool
        """
        status = {
            "socket_alive": False,
            "main_thread_alive": False,
            "pid": None,
            "is_rendering": False,
            "error": None,
        }
        if not self.sock:
            try:
                if not self.connect():
                    status["error"] = "Not connected"
                    return status
            except Exception as e:
                status["error"] = str(e)
                return status

        # 1. Test socket thread responsiveness (ping_thread)
        try:
            self.sock.settimeout(1.0)
            ping_cmd = {"type": "ping_thread", "params": {}}
            self.sock.sendall(json.dumps(ping_cmd).encode("utf-8"))

            response_data = self.receive_full_response(self.sock, timeout=1.0)
            response = json.loads(response_data.decode("utf-8"))

            if response.get("status") == "success":
                result = response.get("result", {})
                status["socket_alive"] = True
                status["pid"] = result.get("pid")
                status["is_rendering"] = result.get("is_rendering", False)
        except Exception as e:
            status["error"] = f"ping_thread failed: {e}"
            self.disconnect()  # Reset connection
            return status

        # 2. Test main thread responsiveness (ping_main)
        if status["socket_alive"]:
            try:
                self.sock.settimeout(2.0)
                ping_cmd = {"type": "ping_main", "params": {}}
                self.sock.sendall(json.dumps(ping_cmd).encode("utf-8"))

                response_data = self.receive_full_response(self.sock, timeout=2.0)
                response = json.loads(response_data.decode("utf-8"))

                if response.get("status") == "success":
                    res = response.get("result", {})
                    if res.get("status") == "pong":
                        status["main_thread_alive"] = True
            except Exception as e:
                status["main_thread_alive"] = False
                status["error"] = f"ping_main timed out/failed: {e}"

        return status


class BlenderWatchdog(threading.Thread):
    def __init__(self, connection, check_interval=5.0, max_unresponsive_seconds=15.0):
        super().__init__()
        self.connection = connection
        self.check_interval = check_interval
        self.max_unresponsive_seconds = max_unresponsive_seconds
        self.daemon = True
        self.running = False
        self.unresponsive_since = None
        self.blender_proc_command = None

    def start_watchdog(self, run_command_args=None):
        self.blender_proc_command = run_command_args
        self.running = True
        self.start()

    def stop_watchdog(self):
        self.running = False

    def run(self):
        logger.info("BlenderWatchdog thread started")
        while self.running:
            time.sleep(self.check_interval)
            if not self.running:
                break

            try:
                status = self.connection.ping_status()
            except Exception as e:
                logger.debug(f"Watchdog ping_status exception: {e}")
                status = {
                    "socket_alive": False,
                    "main_thread_alive": False,
                    "pid": None,
                    "is_rendering": False,
                    "error": str(e),
                }

            if status["socket_alive"]:
                if status["main_thread_alive"] or status["is_rendering"]:
                    self.unresponsive_since = None
                else:
                    if self.unresponsive_since is None:
                        self.unresponsive_since = time.time()

                    elapsed = time.time() - self.unresponsive_since
                    logger.warning(f"Blender main thread is unresponsive for {elapsed:.1f}s")

                    if elapsed >= self.max_unresponsive_seconds:
                        logger.error("Blender main thread has exceeded max unresponsive limit!")
                        self.handle_unresponsive(status["pid"])
            else:
                if self.unresponsive_since is None:
                    self.unresponsive_since = time.time()

                elapsed = time.time() - self.unresponsive_since
                logger.warning(f"Blender socket connection is dead/unresponsive for {elapsed:.1f}s")

                if elapsed >= self.max_unresponsive_seconds:
                    logger.error(
                        "Blender connection is dead and has exceeded max unresponsive limit!"
                    )
                    self.handle_unresponsive(status["pid"])

    def handle_unresponsive(self, pid):
        logger.error("WATCHDOG: Attempting Blender crash recovery...")
        self.unresponsive_since = None  # Reset counter

        if pid:
            try:
                import signal

                logger.info(f"WATCHDOG: Sending SIGKILL to Blender PID {pid}")
                os.kill(pid, signal.SIGKILL)
            except Exception as e:
                logger.error(f"WATCHDOG: Failed to kill Blender process: {e}")

        if self.blender_proc_command:
            try:
                import subprocess

                logger.info(
                    f"WATCHDOG: Restarting Blender with command: {self.blender_proc_command}"
                )
                subprocess.Popen(
                    self.blender_proc_command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                logger.info("WATCHDOG: Blender restart process spawned successfully.")
            except Exception as e:
                logger.error(f"WATCHDOG: Failed to restart Blender: {e}")
        else:
            logger.warning(
                "WATCHDOG: Auto-restart command not configured (BLENDER_LAUNCH_COMMAND). Please restart Blender manually."
            )


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """Manage server startup and shutdown lifecycle"""
    logger.info("BlenderMCP server starting up")

    connection = get_blender_connection()

    launch_cmd_str = os.getenv("BLENDER_LAUNCH_COMMAND")
    blender_args = None
    if launch_cmd_str:
        import shlex

        blender_args = shlex.split(launch_cmd_str)
        logger.info(f"Watchdog auto-restart configured with command: {blender_args}")

    watchdog = BlenderWatchdog(connection, check_interval=5.0, max_unresponsive_seconds=15.0)
    watchdog.start_watchdog(blender_args)

    try:
        yield {}
    finally:
        logger.info("Stopping BlenderWatchdog...")
        watchdog.stop_watchdog()
        connection = _connection_state.get_connection()
        if connection:
            logger.info("Disconnecting from Blender on shutdown")
            connection.disconnect()
            _connection_state.clear()
        logger.info("BlenderMCP server shut down")


class BlenderMCP(FastMCP):
    async def list_tools(self) -> list[Any]:
        # Get all tools from the superclass
        tools = await super().list_tools()

        # Determine the current tool profile
        try:
            blender = get_blender_connection()
            result = blender.send_command("get_mcp_preferences")
            profile = result.get("mcp_tool_profile", "ALL")
        except Exception as e:
            logger.warning(f"Could not retrieve tool profile from Blender, defaulting to ALL: {e}")
            profile = "ALL"

        logger.info(f"Filtering tools for profile: {profile}")
        if profile == "ALL":
            return tools

        # Define allowed tools per profile
        essential_tools = {
            "get_scene_info",
            "get_active_object",
            "set_active_object",
            "get_object_info",
            "transform_object",
            "delete_object",
            "add_primitive",
            "get_viewport_screenshot",
            "execute_blender_code",
            "get_operator_help",
            "list_blender_operators",
            "get_mcp_diagnostics",
        }

        allowed_tools = set(essential_tools)

        if profile == "MODELING":
            allowed_tools.update(
                {
                    "apply_boolean_operation",
                    "set_exact_dimensions",
                    "snap_objects_by_proximity",
                    "separate_loose_parts",
                }
            )
        elif profile == "MATERIALS":
            allowed_tools.update(
                {
                    "download_ambientcg_material",
                    "download_polyhaven_asset",
                    "download_sketchfab_model",
                    "get_polyhaven_categories",
                    "get_polyhaven_status",
                    "get_sketchfab_status",
                    "import_blenderkit_asset",
                    "search_ambientcg_materials",
                    "search_blenderkit",
                    "search_polyhaven_assets",
                    "search_sketchfab_models",
                    "set_texture",
                    "setup_camera",
                    "setup_product_studio",
                }
            )
        elif profile == "PHYSICS":
            allowed_tools.update(
                {
                    "add_physics_constraint",
                    "create_axle_joint",
                    "create_ball_joint",
                    "create_hinge_joint",
                    "setup_physics_body",
                    "run_assembly_simulation",
                    "mark_as_functional_part",
                    "list_functional_parts",
                }
            )
        elif profile == "PRINTING":
            allowed_tools.update(
                {
                    "analyze_structural_properties",
                    "apply_print_thickness",
                    "assign_print_color",
                    "auto_layout_for_printing",
                    "auto_repair_mesh",
                    "check_mesh_integrity",
                    "create_screw_hole",
                    "create_snap_fit",
                    "export_for_printing",
                    "generate_fastener",
                    "resolve_self_intersections",
                    "set_clearance_tolerance",
                }
            )

        filtered = [t for t in tools if t.name in allowed_tools]
        logger.info(f"Exposing {len(filtered)} out of {len(tools)} tools for profile {profile}")
        return filtered


# Create the MCP server with lifespan support
mcp = BlenderMCP("BlenderMCP", lifespan=server_lifespan)

# Resource endpoints


class _ConnectionState:
    """Thread-safe state for persistent addon connection and feature flags."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.connection: BlenderConnection | None = None
        self.polyhaven_enabled = False

    def get_connection(self) -> BlenderConnection | None:
        with self._lock:
            return self.connection

    def set_connection(self, connection: BlenderConnection | None) -> None:
        with self._lock:
            self.connection = connection

    def set_polyhaven_enabled(self, enabled: bool) -> None:
        with self._lock:
            self.polyhaven_enabled = enabled

    def is_polyhaven_enabled(self) -> bool:
        with self._lock:
            return self.polyhaven_enabled

    def clear(self) -> None:
        with self._lock:
            self.connection = None
            self.polyhaven_enabled = False


_connection_state = _ConnectionState()


def get_blender_connection():
    """Get or create a persistent Blender connection"""
    # 1. Fast-path check outside lock
    existing_connection = _connection_state.get_connection()
    if existing_connection is not None:
        try:
            result = existing_connection.send_command("get_polyhaven_status")
            _connection_state.set_polyhaven_enabled(result.get("enabled", False))
            return existing_connection
        except Exception as e:
            logger.warning(f"Existing connection is no longer valid: {str(e)}")
            try:
                existing_connection.disconnect()
            except Exception:
                pass
            _connection_state.clear()

    # 2. Acquire lock for connection creation
    with _connection_state._lock:
        # Double check inside the lock
        existing_connection = _connection_state.get_connection()
        if existing_connection is not None:
            return existing_connection

        host = os.getenv("BLENDER_HOST", DEFAULT_HOST)
        port = int(os.getenv("BLENDER_PORT", DEFAULT_PORT))
        timeout = float(os.getenv("BLENDER_SOCKET_TIMEOUT", DEFAULT_SOCKET_TIMEOUT))
        connect_attempts = int(os.getenv("BLENDER_CONNECT_ATTEMPTS", DEFAULT_CONNECT_ATTEMPTS))
        command_attempts = int(os.getenv("BLENDER_COMMAND_ATTEMPTS", DEFAULT_COMMAND_ATTEMPTS))
        backoff_seconds = float(os.getenv("BLENDER_RETRY_BACKOFF", DEFAULT_RETRY_BACKOFF))

        new_connection = BlenderConnection(
            host=host,
            port=port,
            timeout=timeout,
            connect_attempts=connect_attempts,
            command_attempts=command_attempts,
            backoff_seconds=backoff_seconds,
        )
        if not new_connection.connect():
            logger.error("Failed to connect to Blender")
            raise Exception("Could not connect to Blender. Make sure the Blender addon is running.")

        _connection_state.set_connection(new_connection)
        logger.info("Created new persistent connection to Blender")
        return new_connection


def _prepare_temp_file_path(prefix: str = "blender_screenshot", suffix: str = ".png") -> Path:
    """Return a writable temporary file path, raising helpful errors if unavailable."""
    temp_dir = Path(tempfile.gettempdir())
    if not temp_dir.exists():
        raise FileNotFoundError(
            f"Temporary directory {temp_dir} does not exist. Set TMPDIR to a valid, writable directory and retry."
        )
    if not os.access(temp_dir, os.W_OK):
        raise PermissionError(
            f"Cannot write to temporary directory {temp_dir}. Check permissions or point TMPDIR to a writable location."
        )

    return temp_dir / f"{prefix}_{os.getpid()}{suffix}"


def _cleanup_file(path: Path) -> None:
    """Remove a file while suppressing filesystem errors."""
    try:
        if path.exists():
            path.unlink()
            logger.debug(f"Removed temporary file {path}")
    except Exception as cleanup_error:
        logger.warning(f"Failed to remove temporary file {path}: {cleanup_error}")


def _read_file_with_retry(path: Path, attempts: int = 3, delay: float = 0.2) -> bytes:
    """Read file contents, retrying briefly if the producer is still writing."""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            if not path.exists():
                raise FileNotFoundError(
                    f"Screenshot file was not created at {path}. Ensure the MCP server can write to the temp directory."
                )
            return path.read_bytes()
        except FileNotFoundError as e:
            last_error = e
            if attempt < attempts:
                time.sleep(delay)
        except OSError as e:
            last_error = e
            if attempt < attempts:
                time.sleep(delay)
        else:
            break

        raise last_error


@mcp.tool()
def get_scene_info(
    ctx: Context, filter_type: str = None, filter_name: str = None, limit: int = 100
) -> str:
    """
    Get information about the current Blender scene, including objects and materials.

    Parameters:
    - filter_type: Optional object type to filter by (e.g. 'MESH', 'LIGHT', 'CAMERA')
    - filter_name: Optional partial name to filter objects
    - limit: Maximum number of objects to return (default 100)
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "get_scene_info",
            {"filter_type": filter_type, "filter_name": filter_name, "limit": limit},
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting scene info: {str(e)}")
        return tool_error("Error getting scene info", data={"detail": str(e)})


@mcp.tool()
def get_active_object(ctx: Context) -> str:
    """Get the name and type of the currently active object in Blender."""
    try:
        blender = get_blender_connection()
        result = blender.send_command("get_active_object")
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error getting active object", data={"detail": str(e)})


@mcp.tool()
def set_active_object(ctx: Context, name: str) -> str:
    """Set an object as active and selected by its name."""
    try:
        blender = get_blender_connection()
        result = blender.send_command("set_active_object", {"name": name})
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error setting active object", data={"detail": str(e)})


@mcp.tool()
def transform_object(
    ctx: Context,
    name: str,
    location: list[float] = None,
    rotation: list[float] = None,
    scale: list[float] = None,
    relative: bool = False,
) -> str:
    """
    Precisely transform an object's location, rotation, and scale.

    Parameters:
    - name: Name of the object
    - location: List of [x, y, z] coordinates
    - rotation: List of [x, y, z] Euler angles in degrees
    - scale: List of [x, y, z] scale factors
    - relative: If True, transformations are relative to current values
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "transform_object",
            {
                "name": name,
                "location": location,
                "rotation": rotation,
                "scale": scale,
                "relative": relative,
            },
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error transforming object", data={"detail": str(e)})


@mcp.tool()
def add_primitive(
    ctx: Context,
    type: str,
    name: str = None,
    location: list[float] = [0, 0, 0],
    scale: list[float] = [1, 1, 1],
) -> str:
    """
    Add a new primitive object (Cube, Sphere, etc.) to the scene.

    Parameters:
    - type: Type of primitive ('CUBE', 'SPHERE', 'PLANE', 'MONKEY', 'CYLINDER', 'CONE', 'TORUS')
    - name: Optional name for the new object
    - location: [x, y, z] position
    - scale: [x, y, z] scale
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "add_primitive", {"type": type, "name": name, "location": location, "scale": scale}
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error adding primitive", data={"detail": str(e)})


@mcp.tool()
def delete_object(ctx: Context, name: str) -> str:
    """Delete an object from the scene by its name."""
    try:
        blender = get_blender_connection()
        result = blender.send_command("delete_object", {"name": name})
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error deleting object", data={"detail": str(e)})


@mcp.tool()
def list_blender_operators(ctx: Context, filter_text: str = "") -> str:
    """
    List available Blender operators (bpy.ops), optionally filtered.
    Useful for discovering what commands can be executed via execute_blender_code.
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("list_blender_operators", {"filter_text": filter_text})
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error listing operators", data={"detail": str(e)})


@mcp.tool()
def get_operator_help(ctx: Context, operator_name: str) -> str:
    """Get documentation and parameters for a specific Blender operator (e.g. 'bpy.ops.mesh.subdivide')."""
    try:
        blender = get_blender_connection()
        result = blender.send_command("get_operator_help", {"operator_name": operator_name})
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error getting operator help", data={"detail": str(e)})


@mcp.tool()
def get_object_info(ctx: Context, object_name: str) -> str:
    """
    Get detailed information about a specific object in the Blender scene.

    Parameters:
    - object_name: The name of the object to get information about
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("get_object_info", {"name": object_name})

        # Just return the JSON representation of what Blender sent us
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting object info from Blender: {str(e)}")
        return tool_error(
            "Error getting object info", data={"detail": str(e), "object_name": object_name}
        )


@mcp.tool()
def get_viewport_screenshot(ctx: Context, max_size: int = 800) -> Image:
    """
    Capture a screenshot of the current Blender 3D viewport.

    Parameters:
    - max_size: Maximum size in pixels for the largest dimension (default: 800)

    Returns the screenshot as an Image.
    """
    t0 = time.time()
    temp_path = _prepare_temp_file_path()
    try:
        blender = get_blender_connection()

        result = blender.send_command(
            "get_viewport_screenshot",
            {"max_size": max_size, "filepath": str(temp_path), "format": "png"},
        )

        if "error" in result:
            raise Exception(result["error"])

        image_bytes = _read_file_with_retry(temp_path)

        perf_metrics.inc("viewport_screenshot_success")
        perf_metrics.observe("viewport_screenshot_latency", time.time() - t0)
        return Image(data=image_bytes, format="png")

    except Exception as e:
        logger.error(f"Error capturing screenshot: {str(e)}")
        perf_metrics.inc("viewport_screenshot_error")
        perf_metrics.observe("viewport_screenshot_latency", time.time() - t0)
        guidance = (
            "Screenshot failed: "
            f"{str(e)}. Check that Blender can write to {temp_path.parent} "
            "or set TMPDIR to a writable directory, then try again."
        )
        raise Exception(guidance)
    finally:
        _cleanup_file(temp_path)


@mcp.tool()
def execute_blender_code(ctx: Context, code: str) -> str:
    """
    Execute arbitrary Python code in Blender. Make sure to do it step-by-step by breaking it into smaller chunks.

    Parameters:
    - code: The Python code to execute
    """
    try:
        # Get the global connection
        blender = get_blender_connection()
        result = blender.send_command("execute_code", {"code": code})
        return f"Code executed successfully: {result.get('result', '')}"
    except Exception as e:
        logger.error(f"Error executing code: {str(e)}")
        return tool_error("Error executing code", data={"detail": str(e)})


@mcp.tool()
def get_polyhaven_categories(ctx: Context, asset_type: str = "hdris") -> str:
    """
    Get a list of categories for a specific asset type on Polyhaven.

    Parameters:
    - asset_type: The type of asset to get categories for (hdris, textures, models, all)
    """
    try:
        blender = get_blender_connection()
        if not _connection_state.is_polyhaven_enabled():
            return "PolyHaven integration is disabled. Select it in the sidebar in BlenderMCP, then run it again."
        result = blender.send_command("get_polyhaven_categories", {"asset_type": asset_type})

        if "error" in result:
            return tool_error("PolyHaven category lookup failed", data={"detail": result["error"]})

        # Format the categories in a more readable way
        categories = result["categories"]
        formatted_output = f"Categories for {asset_type}:\n\n"

        # Sort categories by count (descending)
        sorted_categories = sorted(categories.items(), key=lambda x: x[1], reverse=True)

        for category, count in sorted_categories:
            formatted_output += f"- {category}: {count} assets\n"

        return formatted_output
    except Exception as e:
        logger.error(f"Error getting Polyhaven categories: {str(e)}")
        return tool_error("Error getting PolyHaven categories", data={"detail": str(e)})


@mcp.tool()
def search_polyhaven_assets(ctx: Context, asset_type: str = "all", categories: str = None) -> str:
    """
    Search for assets on Polyhaven with optional filtering.

    Parameters:
    - asset_type: Type of assets to search for (hdris, textures, models, all)
    - categories: Optional comma-separated list of categories to filter by

    Returns a list of matching assets with basic information.
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "search_polyhaven_assets", {"asset_type": asset_type, "categories": categories}
        )

        if "error" in result:
            return tool_error("PolyHaven search failed", data={"detail": result["error"]})

        # Format the assets in a more readable way
        assets = result["assets"]
        total_count = result["total_count"]
        returned_count = result["returned_count"]

        formatted_output = f"Found {total_count} assets"
        if categories:
            formatted_output += f" in categories: {categories}"
        formatted_output += f"\nShowing {returned_count} assets:\n\n"

        # Sort assets by download count (popularity)
        sorted_assets = sorted(
            assets.items(), key=lambda x: x[1].get("download_count", 0), reverse=True
        )

        for asset_id, asset_data in sorted_assets:
            formatted_output += f"- {asset_data.get('name', asset_id)} (ID: {asset_id})\n"
            formatted_output += (
                f"  Type: {['HDRI', 'Texture', 'Model'][asset_data.get('type', 0)]}\n"
            )
            formatted_output += f"  Categories: {', '.join(asset_data.get('categories', []))}\n"
            formatted_output += f"  Downloads: {asset_data.get('download_count', 'Unknown')}\n\n"

        return formatted_output
    except Exception as e:
        logger.error(f"Error searching Polyhaven assets: {str(e)}")
        return tool_error("Error searching PolyHaven assets", data={"detail": str(e)})


@mcp.tool()
def download_polyhaven_asset(
    ctx: Context, asset_id: str, asset_type: str, resolution: str = "1k", file_format: str = None
) -> str:
    """
    Download and import a Polyhaven asset into Blender.

    Parameters:
    - asset_id: The ID of the asset to download
    - asset_type: The type of asset (hdris, textures, models)
    - resolution: The resolution to download (e.g., 1k, 2k, 4k)
    - file_format: Optional file format (e.g., hdr, exr for HDRIs; jpg, png for textures; gltf, fbx for models)

    Returns a message indicating success or failure.
    """
    # Validate inputs
    from blender_mcp.shared.validators import (
        ValidationError,
        validate_asset_id,
        validate_resolution,
    )

    try:
        asset_id = validate_asset_id(asset_id)
    except ValidationError as e:
        return tool_error("Invalid asset ID", data={"detail": str(e), "asset_id": asset_id})

    if asset_type not in ["hdris", "textures", "models"]:
        return tool_error(
            "Invalid asset type",
            data={"detail": "Must be one of: hdris, textures, models", "asset_type": asset_type},
        )

    try:
        resolution = validate_resolution(resolution)
    except ValidationError as e:
        return tool_error("Invalid resolution", data={"detail": str(e), "resolution": resolution})

    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "download_polyhaven_asset",
            {
                "asset_id": asset_id,
                "asset_type": asset_type,
                "resolution": resolution,
                "file_format": file_format,
            },
        )

        if "error" in result:
            return tool_error(
                "PolyHaven download failed", data={"detail": result["error"], "asset_id": asset_id}
            )

        if result.get("success"):
            message = result.get("message", "Asset downloaded and imported successfully")

            # Add additional information based on asset type
            if asset_type == "hdris":
                return f"{message}. The HDRI has been set as the world environment."
            elif asset_type == "textures":
                material_name = result.get("material", "")
                maps = ", ".join(result.get("maps", []))
                return f"{message}. Created material '{material_name}' with maps: {maps}."
            elif asset_type == "models":
                return f"{message}. The model has been imported into the current scene."
            else:
                return message
        else:
            return tool_error(
                "Failed to download asset",
                data={
                    "detail": result.get("message", "Unknown error"),
                    "asset_id": asset_id,
                    "asset_type": asset_type,
                },
            )
    except Exception as e:
        logger.error(f"Error downloading Polyhaven asset: {str(e)}")
        return tool_error(
            "Error downloading PolyHaven asset", data={"detail": str(e), "asset_id": asset_id}
        )


@mcp.tool()
def set_texture(ctx: Context, object_name: str, texture_id: str) -> str:
    """
    Apply a previously downloaded Polyhaven texture to an object.

    Parameters:
    - object_name: Name of the object to apply the texture to
    - texture_id: ID of the Polyhaven texture to apply (must be downloaded first)

    Returns a message indicating success or failure.
    """
    # Validate inputs
    from blender_mcp.shared.validators import ValidationError, validate_asset_id

    if not object_name or not isinstance(object_name, str):
        return tool_error(
            "Invalid object name", data={"detail": "Object name must be a non-empty string"}
        )

    try:
        texture_id = validate_asset_id(texture_id)
    except ValidationError as e:
        return tool_error("Invalid texture ID", data={"detail": str(e), "texture_id": texture_id})

    try:
        # Get the global connection
        blender = get_blender_connection()
        result = blender.send_command(
            "set_texture", {"object_name": object_name, "texture_id": texture_id}
        )

        if "error" in result:
            return tool_error(
                "Failed to apply texture",
                data={
                    "detail": result["error"],
                    "object_name": object_name,
                    "texture_id": texture_id,
                },
            )

        if result.get("success"):
            material_name = result.get("material", "")
            maps = ", ".join(result.get("maps", []))

            # Add detailed material info
            material_info = result.get("material_info", {})
            node_count = material_info.get("node_count", 0)
            has_nodes = material_info.get("has_nodes", False)
            texture_nodes = material_info.get("texture_nodes", [])

            output = f"Successfully applied texture '{texture_id}' to {object_name}.\n"
            output += f"Using material '{material_name}' with maps: {maps}.\n\n"
            output += f"Material has nodes: {has_nodes}\n"
            output += f"Total node count: {node_count}\n\n"

            if texture_nodes:
                output += "Texture nodes:\n"
                for node in texture_nodes:
                    output += f"- {node['name']} using image: {node['image']}\n"
                    if node["connections"]:
                        output += "  Connections:\n"
                        for conn in node["connections"]:
                            output += f"    {conn}\n"
            else:
                output += "No texture nodes found in the material.\n"

            return output
        else:
            return tool_error(
                "Failed to apply texture",
                data={
                    "detail": result.get("message", "Unknown error"),
                    "object_name": object_name,
                    "texture_id": texture_id,
                },
            )
    except Exception as e:
        logger.error(f"Error applying texture: {str(e)}")
        return tool_error(
            "Error applying texture", data={"detail": str(e), "texture_id": texture_id}
        )


@mcp.tool()
def get_polyhaven_status(ctx: Context) -> str:
    """
    Check if PolyHaven integration is enabled in Blender.
    Returns a message indicating whether PolyHaven features are available.
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("get_polyhaven_status")
        enabled = result.get("enabled", False)
        message = result.get("message", "")
        if enabled:
            message += (
                "PolyHaven is good at Textures, and has a wider variety of textures than Sketchfab."
            )
        return message
    except Exception as e:
        logger.error(f"Error checking PolyHaven status: {str(e)}")
        return tool_error("Error checking PolyHaven status", data={"detail": str(e)})


@mcp.tool()
def get_sketchfab_status(ctx: Context) -> str:
    """
    Check if Sketchfab integration is enabled in Blender.
    Returns a message indicating whether Sketchfab features are available.
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("get_sketchfab_status")
        enabled = result.get("enabled", False)
        message = result.get("message", "")
        if enabled:
            message += "Sketchfab is good at Realistic models, and has a wider variety of models than PolyHaven."
        return message
    except Exception as e:
        logger.error(f"Error checking Sketchfab status: {str(e)}")
        return tool_error("Error checking Sketchfab status", data={"detail": str(e)})


@mcp.tool()
def get_mcp_diagnostics(ctx: Context) -> str:
    """Return MCP server diagnostics (metrics + Blender connectivity probe)."""
    diagnostics: dict[str, Any] = {
        "perf_metrics": perf_metrics.report(),
        "connection": {
            "host": os.getenv("BLENDER_HOST", DEFAULT_HOST),
            "port": int(os.getenv("BLENDER_PORT", DEFAULT_PORT)),
            "reachable": False,
        },
    }

    try:
        blender = get_blender_connection()
        scene_info = blender.send_command("get_scene_info")
        diagnostics["connection"]["reachable"] = True
        diagnostics["scene_probe"] = {
            "name": scene_info.get("name"),
            "object_count": scene_info.get("object_count"),
            "materials_count": scene_info.get("materials_count"),
        }
    except Exception as exc:
        diagnostics["connection"]["error"] = str(exc)

    return json.dumps(diagnostics, indent=2)


@mcp.tool()
def search_sketchfab_models(
    ctx: Context, query: str, categories: str = None, count: int = 20, downloadable: bool = True
) -> str:
    """
    Search for models on Sketchfab with optional filtering.

    Parameters:
    - query: Text to search for
    - categories: Optional comma-separated list of categories
    - count: Maximum number of results to return (default 20)
    - downloadable: Whether to include only downloadable models (default True)

    Returns a formatted list of matching models.
    """
    # Validate inputs
    if not query or not isinstance(query, str):
        return tool_error("Invalid query", data={"detail": "Query must be a non-empty string"})

    if len(query) > 200:
        return tool_error(
            "Query too long", data={"detail": "Max 200 characters", "length": len(query)}
        )

    if not isinstance(count, int) or count < 1 or count > 100:
        return tool_error(
            "Invalid count", data={"detail": "Count must be between 1 and 100", "count": count}
        )

    t0 = time.time()
    try:
        blender = get_blender_connection()
        logger.info(
            f"Searching Sketchfab models with query: {query}, categories: {categories}, count: {count}, downloadable: {downloadable}"
        )
        result = blender.send_command(
            "search_sketchfab_models",
            {
                "query": query,
                "categories": categories,
                "count": count,
                "downloadable": downloadable,
            },
        )

        if "error" in result:
            logger.error(f"Error from Sketchfab search: {result['error']}")
            perf_metrics.inc("sketchfab_search_error")
            perf_metrics.observe("sketchfab_search_latency", time.time() - t0)
            return tool_error(
                "Sketchfab search failed", data={"detail": result["error"], "query": query}
            )

        # Safely get results with fallbacks for None
        if result is None:
            logger.error("Received None result from Sketchfab search")
            perf_metrics.inc("sketchfab_search_error")
            perf_metrics.observe("sketchfab_search_latency", time.time() - t0)
            return tool_error("Sketchfab search returned no data", data={"query": query})

        # Format the results
        models = result.get("results", []) or []
        if not models:
            perf_metrics.inc("sketchfab_search_empty")
            perf_metrics.observe("sketchfab_search_latency", time.time() - t0)
            return f"No models found matching '{query}'"

        formatted_output = f"Found {len(models)} models matching '{query}':\n\n"

        for model in models:
            if model is None:
                continue

            model_name = model.get("name", "Unnamed model")
            model_uid = model.get("uid", "Unknown ID")
            formatted_output += f"- {model_name} (UID: {model_uid})\n"

            # Get user info with safety checks
            user = model.get("user") or {}
            username = (
                user.get("username", "Unknown author")
                if isinstance(user, dict)
                else "Unknown author"
            )
            formatted_output += f"  Author: {username}\n"

            # Get license info with safety checks
            license_data = model.get("license") or {}
            license_label = (
                license_data.get("label", "Unknown")
                if isinstance(license_data, dict)
                else "Unknown"
            )
            formatted_output += f"  License: {license_label}\n"

            # Add face count and downloadable status
            face_count = model.get("faceCount", "Unknown")
            is_downloadable = "Yes" if model.get("isDownloadable") else "No"
            formatted_output += f"  Face count: {face_count}\n"
            formatted_output += f"  Downloadable: {is_downloadable}\n\n"

        perf_metrics.inc("sketchfab_search_success")
        perf_metrics.observe("sketchfab_search_latency", time.time() - t0)
        return formatted_output
    except Exception as e:
        logger.error(f"Error searching Sketchfab models: {str(e)}")
        import traceback

        logger.error(traceback.format_exc())
        perf_metrics.inc("sketchfab_search_error")
        perf_metrics.observe("sketchfab_search_latency", time.time() - t0)
        return tool_error(
            "Error searching Sketchfab models", data={"detail": str(e), "query": query}
        )


@mcp.tool()
def download_sketchfab_model(ctx: Context, uid: str) -> str:
    """
    Download and import a Sketchfab model by its UID.

    Parameters:
    - uid: The unique identifier of the Sketchfab model

    Returns a message indicating success or failure.
    The model must be downloadable and you must have proper access rights.
    """
    # Validate UID
    from blender_mcp.shared.validators import ValidationError, validate_asset_id

    try:
        uid = validate_asset_id(uid)
    except ValidationError as e:
        return tool_error("Invalid model UID", data={"detail": str(e), "uid": uid})

    try:
        blender = get_blender_connection()
        logger.info(f"Attempting to download Sketchfab model with UID: {uid}")

        result = blender.send_command("download_sketchfab_model", {"uid": uid})

        if result is None:
            logger.error("Received None result from Sketchfab download")
            return tool_error("Sketchfab download returned no data", data={"uid": uid})

        if "error" in result:
            logger.error(f"Error from Sketchfab download: {result['error']}")
            return tool_error(
                "Sketchfab download failed", data={"detail": result["error"], "uid": uid}
            )

        if result.get("success"):
            imported_objects = result.get("imported_objects", [])
            object_names = ", ".join(imported_objects) if imported_objects else "none"
            return f"Successfully imported model. Created objects: {object_names}"
        else:
            return tool_error(
                "Failed to download model",
                data={"detail": result.get("message", "Unknown error"), "uid": uid},
            )
    except Exception as e:
        logger.error(f"Error downloading Sketchfab model: {str(e)}")
        import traceback

        logger.error(traceback.format_exc())
        return tool_error("Error downloading Sketchfab model", data={"detail": str(e), "uid": uid})


@mcp.tool()
def search_ambientcg_materials(ctx: Context, query: str = "", limit: int = 20) -> str:
    """
    Search for PBR materials on AmbientCG.

    Parameters:
    - query: Text to search for (e.g., 'brick', 'wood', 'metal')
    - limit: Maximum results to return (default 20)
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "search_ambientcg_materials", {"query": query, "limit": limit}
        )
        if "error" in result:
            return tool_error("AmbientCG search failed", data={"detail": result["error"]})

        materials = result.get("materials", [])
        if not materials:
            return f"No AmbientCG materials found matching '{query}'"

        output = f"Found {len(materials)} AmbientCG materials:\n\n"
        for mat in materials:
            output += f"- {mat.get('assetId')} (Category: {mat.get('category')})\n"
        return output
    except Exception as e:
        return tool_error("Error searching AmbientCG", data={"detail": str(e)})


@mcp.tool()
def download_ambientcg_material(
    ctx: Context, asset_id: str, resolution: str = "2K", file_format: str = "JPG"
) -> str:
    """
    Download and import an AmbientCG material.

    Parameters:
    - asset_id: The ID of the material (e.g., 'Bricks001')
    - resolution: Desired resolution (e.g., '1K', '2K', '4K', '8K')
    - file_format: Format (usually 'JPG' or 'PNG')
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "download_ambientcg_material",
            {"asset_id": asset_id, "resolution": resolution, "file_format": file_format},
        )
        if "error" in result:
            return tool_error("AmbientCG download failed", data={"detail": result["error"]})
        return f"Successfully imported material '{asset_id}' from AmbientCG."
    except Exception as e:
        return tool_error("Error downloading AmbientCG material", data={"detail": str(e)})


# 3D Printing Tools
@mcp.tool()
def set_exact_dimensions(
    ctx: Context,
    object_name: str,
    size_x: float = None,
    size_y: float = None,
    size_z: float = None,
) -> str:
    """Set exact dimensions (in mm) for an object. Useful for precision engineering."""
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "set_exact_dimensions",
            {"object_name": object_name, "size_x": size_x, "size_y": size_y, "size_z": size_z},
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error setting dimensions", data={"detail": str(e)})


@mcp.tool()
def apply_print_thickness(ctx: Context, object_name: str, thickness_mm: float = 2.0) -> str:
    """Apply a shell thickness to a mesh for 3D printing (Solidify)."""
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "apply_print_thickness", {"object_name": object_name, "thickness_mm": thickness_mm}
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error applying thickness", data={"detail": str(e)})


@mcp.tool()
def auto_layout_for_printing(
    ctx: Context, bed_size_x: float = 256, bed_size_y: float = 256, padding_mm: float = 5
) -> str:
    """Automatically arrange all meshes on the print bed (Z=0)."""
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "auto_layout_for_printing",
            {"bed_size_x": bed_size_x, "bed_size_y": bed_size_y, "padding_mm": padding_mm},
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error layouting for print", data={"detail": str(e)})


# Mesh Tools
@mcp.tool()
def check_mesh_integrity(ctx: Context, object_name: str) -> str:
    """Analyze mesh for non-manifold geometry, holes, and printing issues."""
    try:
        blender = get_blender_connection()
        result = blender.send_command("check_mesh_integrity", {"object_name": object_name})
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error checking mesh", data={"detail": str(e)})


@mcp.tool()
def auto_repair_mesh(ctx: Context, object_name: str) -> str:
    """Attempt to automatically fix common non-manifold issues in a mesh."""
    try:
        blender = get_blender_connection()
        result = blender.send_command("auto_repair_mesh", {"object_name": object_name})
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error repairing mesh", data={"detail": str(e)})


@mcp.tool()
def resolve_self_intersections(ctx: Context, object_name: str) -> str:
    """
    Resolve self-intersecting faces within a mesh while preserving its shape.
    Useful for making objects watertight for 3D printing without remeshing.
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("resolve_self_intersections", {"object_name": object_name})
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error resolving self-intersections", data={"detail": str(e)})


# Studio & Rigging
@mcp.tool()
def setup_product_studio(ctx: Context, theme: str = "CLEAN") -> str:
    """Setup a professional lighting and backdrop stúdio for products (options: CLEAN, DARK, COLORFUL)."""
    try:
        blender = get_blender_connection()
        result = blender.send_command("setup_product_studio", {"theme": theme})
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error setting up studio", data={"detail": str(e)})


@mcp.tool()
def apply_boolean_operation(
    ctx: Context, target_name: str, tool_name: str, operation: str = "DIFFERENCE"
) -> str:
    """Apply boolean (Difference, Union, Intersect) using tool_name obj on target_name obj."""
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "apply_boolean_operation",
            {"target_name": target_name, "tool_name": tool_name, "operation": operation},
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error in boolean op", data={"detail": str(e)})


@mcp.tool()
def export_for_printing(
    ctx: Context, object_names: list[str], filepath: str, format: str = "STL"
) -> str:
    """Export specified objects for 3D printing (STL or OBJ)."""
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "export_for_printing", {"object_names": object_names, "filepath": filepath}
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error exporting", data={"detail": str(e)})


@mcp.tool()
def assign_print_color(ctx: Context, object_name: str, hex_color: str) -> str:
    """Assign a base color (Hex) to an object for multi-color printing."""
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "assign_print_color", {"object_name": object_name, "hex_color": hex_color}
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error assigning color", data={"detail": str(e)})


@mcp.tool()
def separate_loose_parts(ctx: Context, object_name: str, smart_rename: bool = True) -> str:
    """Separate a single object into multiple objects based on loose geometry parts."""
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "separate_loose_parts", {"object_name": object_name, "smart_rename": smart_rename}
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error separating parts", data={"detail": str(e)})


@mcp.tool()
def setup_camera(
    ctx: Context,
    focus_object_name: str = None,
    location: list[float] = [0, -10, 5],
    create_new: bool = False,
) -> str:
    """Setup or create a camera looking at focus_object_name."""
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "setup_camera",
            {
                "focus_object_name": focus_object_name,
                "location": location,
                "create_new": create_new,
            },
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error setting up camera", data={"detail": str(e)})


@mcp.tool()
def create_axle_joint(
    ctx: Context,
    chassis_name: str,
    wheel_name: str,
    axle_diameter: float = None,
    clearance: float = 0.2,
) -> str:
    """
    Create a mechanical axle joint (hole in chassis, pin on wheel).

    Parameters:
    - chassis_name: Name of the object acting as the chassis
    - wheel_name: Name of the object acting as the wheel
    - axle_diameter: Diameter of the axle in mm (optional)
    - clearance: Side clearance in mm (default 0.2)
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "create_axle_joint",
            {
                "chassis_name": chassis_name,
                "wheel_name": wheel_name,
                "axle_diameter": axle_diameter,
                "clearance": clearance,
            },
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error creating axle joint", data={"detail": str(e)})


@mcp.tool()
def create_hinge_joint(
    ctx: Context,
    part1_name: str,
    part2_name: str,
    diameter: float = 3.0,
    clearance: float = 0.2,
) -> str:
    """
    Create a hinge joint (pivot holes) between two parts.

    Parameters:
    - part1_name: Name of the first part
    - part2_name: Name of the second part
    - diameter: Diameter of the hinge pin in mm (default 3.0)
    - clearance: Hole clearance in mm (default 0.2)
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "create_hinge_joint",
            {
                "part1_name": part1_name,
                "part2_name": part2_name,
                "diameter": diameter,
                "clearance": clearance,
            },
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error creating hinge", data={"detail": str(e)})


@mcp.tool()
def create_snap_fit(
    ctx: Context,
    female_part_name: str,
    male_part_name: str,
    width: float = 10.0,
    height: float = 15.0,
    thickness: float = 2.0,
) -> str:
    """
    Create a cantilever snap-fit joint between two parts.

    Parameters:
    - female_part_name: Part that will have the receiving hole
    - male_part_name: Part that will have the hook/tab
    - width: Width of the snap tab in mm (default 10)
    - height: Height of the snap tab in mm (default 15)
    - thickness: Thickness of the tab in mm (default 2)
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "create_snap_fit",
            {
                "female_part_name": female_part_name,
                "male_part_name": male_part_name,
                "width": width,
                "height": height,
                "thickness": thickness,
            },
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error creating snap-fit", data={"detail": str(e)})


@mcp.tool()
def snap_objects_by_proximity(
    ctx: Context, source_name: str, target_name: str, padding_mm: float = 0.0
) -> str:
    """
    Snap a source object to the closest surface of a target object.

    Parameters:
    - source_name: Object to be moved
    - target_name: Object to snap against
    - padding_mm: Distance to maintain from the surface in mm (default 0)
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "snap_objects_by_proximity",
            {"source_name": source_name, "target_name": target_name, "padding_mm": padding_mm},
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error snapping objects", data={"detail": str(e)})


@mcp.tool()
def mark_as_functional_part(
    ctx: Context, object_name: str, role: str = "Generic", metadata: dict = None
) -> str:
    """
    Tag an object as a functional part and store metadata for management.

    Parameters:
    - object_name: Name of the object to tag
    - role: Descriptive role (e.g., 'Chassis', 'Gear', 'Enclosure')
    - metadata: Optional dictionary of additional properties (e.g., {'material': 'PETG'})
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "mark_as_functional_part",
            {"object_name": object_name, "role": role, "metadata": metadata},
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error marking part", data={"detail": str(e)})


@mcp.tool()
def list_functional_parts(ctx: Context) -> str:
    """List all objects tagged as functional parts in the scene with their metadata."""
    try:
        blender = get_blender_connection()
        result = blender.send_command("list_functional_parts")
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error listing parts", data={"detail": str(e)})


@mcp.tool()
def create_ball_joint(
    ctx: Context,
    socket_part_name: str,
    ball_part_name: str,
    diameter: float = 10.0,
    clearance: float = 0.2,
) -> str:
    """
    Create a ball-and-socket joint between two parts.

    Parameters:
    - socket_part_name: Name of the part that will have the socket
    - ball_part_name: Name of the part that will have the ball
    - diameter: Diameter of the ball in mm (default 10)
    - clearance: Clearance between ball and socket in mm (default 0.2)
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "create_ball_joint",
            {
                "socket_part_name": socket_part_name,
                "ball_part_name": ball_part_name,
                "diameter": diameter,
                "clearance": clearance,
            },
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error creating ball joint", data={"detail": str(e)})


@mcp.tool()
def create_screw_hole(
    ctx: Context,
    part1_name: str,
    part2_name: str = None,
    screw_type: str = "M3",
    countersink: bool = True,
    threaded_insert: bool = False,
    nut_pocket: bool = False,
) -> str:
    """
    Create aligned screw holes for standard metric screws (M2 to M5), with support for 3D printing heat-set inserts or captured hex nuts.

    Parameters:
    - part1_name: Part that will receive the screw head/insert (with optional countersink/insert pocket)
    - part2_name: Optional second part to also receive the aligned hole (and nut pocket if enabled)
    - screw_type: Metric size (Options: M2, M2.5, M3, M4, M5). Default is M3.
    - countersink: Whether to create a recess for the screw head (default True). Ignored if threaded_insert is True.
    - threaded_insert: Wider pocket to accommodate standard brass heat-set threaded inserts (default False).
    - nut_pocket: Hexagonal pocket to capture a standard ISO hex nut (placed on part2 if provided, else part1) (default False).
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "create_screw_hole",
            {
                "part1_name": part1_name,
                "part2_name": part2_name,
                "screw_type": screw_type,
                "countersink": countersink,
                "threaded_insert": threaded_insert,
                "nut_pocket": nut_pocket,
            },
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error creating screw hole", data={"detail": str(e)})


@mcp.tool()
def set_clearance_tolerance(ctx: Context, object_name: str, tolerance_mm: float = 0.2) -> str:
    """
    Apply a shell offset/tolerance to a mesh to ensure precise fit.

    Parameters:
    - object_name: Name of the object to adjust
    - tolerance_mm: Offset distance in mm (positive expands, negative contracts, default 0.2)
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "set_clearance_tolerance", {"object_name": object_name, "tolerance_mm": tolerance_mm}
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error setting tolerance", data={"detail": str(e)})


@mcp.tool()
def search_blenderkit(
    ctx: Context, query: str, asset_type: str = "model", free_only: bool = True
) -> str:
    """
    Search BlenderKit for assets (models, materials, textures, hdr, brush).
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "blenderkit.search_blenderkit",
            {"query": query, "asset_type": asset_type, "free_only": free_only},
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error searching BlenderKit", data={"detail": str(e)})


@mcp.tool()
def import_blenderkit_asset(ctx: Context, asset_id: str) -> str:
    """
    Import a BlenderKit asset by ID into the scene.
    Note: Highly complex/paid assets might require the official BlenderKit addon to be logged in.
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("blenderkit.import_blenderkit_asset", {"asset_id": asset_id})
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error importing from BlenderKit", data={"detail": str(e)})


@mcp.tool()
def setup_physics_body(
    ctx: Context,
    object_name: str,
    body_type: str = "ACTIVE",
    mass: float = 1.0,
    collision_shape: str = "MESH",
) -> str:
    """
    Configure a 3D object to behave as a physics rigid body during mechanical simulations.

    Parameters:
    - object_name: The name of the object to configure
    - body_type: Physics type, either 'ACTIVE' (moving parts) or 'PASSIVE' (static grounds/chassis)
    - mass: Mass of the object in kilograms (default 1.0)
    - collision_shape: Collision boundary type, e.g. 'MESH' (precise), 'BOX', 'CONVEX_HULL', 'CYLINDER'
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "setup_physics_body",
            {
                "object_name": object_name,
                "body_type": body_type,
                "mass": mass,
                "collision_shape": collision_shape,
            },
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error configuring physics body", data={"detail": str(e)})


@mcp.tool()
def add_physics_constraint(
    ctx: Context,
    object1_name: str,
    object2_name: str,
    constraint_type: str = "HINGE",
    location: list[float] = None,
    axis: list[float] = [0, 0, 1],
) -> str:
    """
    Connect two physics bodies with a mechanical joint/constraint (e.g. Hinge, Slider, Piston) for simulation.

    Parameters:
    - object1_name: First connected rigid body object name
    - object2_name: Second connected rigid body object name
    - constraint_type: Joint type, options: 'HINGE' (rotation), 'SLIDER' (linear movement), 'GENERIC_SPRING' (suspension springs), 'FIXED'
    - location: Point of pivot coordinates [x, y, z] in meters (defaults to midpoint)
    - axis: Rotation or sliding axis vector [x, y, z] (default [0, 0, 1])
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "add_physics_constraint",
            {
                "object1_name": object1_name,
                "object2_name": object2_name,
                "constraint_type": constraint_type,
                "location": location,
                "axis": axis,
            },
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error adding physics constraint", data={"detail": str(e)})


@mcp.tool()
def run_assembly_simulation(
    ctx: Context,
    end_frame: int = 100,
    check_pairs: list[list[str]] = None,
) -> str:
    """
    Run the rigid body simulation and perform a frame-by-frame mesh collision check (using BVHTree) to detect mechanical interferences.

    Parameters:
    - end_frame: Duration of simulation in frames to evaluate (default 100)
    - check_pairs: List of pairs of object names to check for collisions, e.g. [["Tire", "Chassis"], ["Rod", "Knuckle"]]
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "run_assembly_simulation",
            {
                "end_frame": end_frame,
                "check_pairs": check_pairs,
            },
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error running assembly simulation", data={"detail": str(e)})


@mcp.tool()
def generate_fastener(
    ctx: Context,
    type: str = "SCREW",
    size: str = "M3",
    length: float = 10.0,
    head_type: str = "SOCKET",
    location: list[float] = [0.0, 0.0, 0.0],
    axis: list[float] = [0.0, 0.0, 1.0],
) -> str:
    """
    Generate a standard metric fastener (Screw, Nut, Washer, Bearing) procedurally in the active Blender scene.

    Parameters:
    - type: Fastener type, options: 'SCREW', 'NUT', 'WASHER', 'BEARING'
    - size: ISO size name (e.g. 'M2', 'M2.5', 'M3', 'M4', 'M5', 'M6', 'M8' for screws/nuts/washers; or '608', '623', '625', '688' for bearings)
    - length: Length of screw shaft in millimeters (only applicable to SCREW)
    - head_type: Screw head type, options: 'SOCKET', 'HEX', 'BUTTON' (only applicable to SCREW)
    - location: Coordinates [x, y, z] in meters where the fastener should be placed
    - axis: Placement axis vector [x, y, z] (default [0, 0, 1])
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "generate_fastener",
            {
                "type": type,
                "size": size,
                "length": length,
                "head_type": head_type,
                "location": location,
                "axis": axis,
            },
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error generating fastener", data={"detail": str(e)})


@mcp.tool()
def analyze_structural_properties(
    ctx: Context,
    object_name: str,
    material_preset: str = "PLA",
) -> str:
    """
    Calculate the estimated weight, center of mass, volume, and identify potential weak spots or stress concentrators for 3D printing of a mesh object.

    Parameters:
    - object_name: The name of the mesh object to analyze in the Blender scene
    - material_preset: Material preset for density and cost estimation (options: 'PLA', 'PETG', 'ABS', 'NYLON', 'STEEL', 'ALUMINUM')
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command(
            "analyze_structural_properties",
            {
                "object_name": object_name,
                "material_preset": material_preset,
            },
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return tool_error("Error analyzing structural properties", data={"detail": str(e)})


@mcp.prompt()
def asset_creation_strategy() -> str:
    """Defines the preferred strategy for creating assets in Blender v2.0."""
    return """Ao criar conteúdo 3D no Blender, use a seguinte hierarquia de ferramentas:

    1. VERIFICAÇÃO DE ESTADO:
       - Use get_scene_info() para entender o que já existe.
       - Use get_viewport_screenshot() para ver visualmente o progresso.

    2. AQUISIÇÃO DE ASSETS (Hierarquia):
       a. BlenderKit: Use primeiro para modelos, materiais e texturas (maior variedade integrada).
       b. PolyHaven: Use para HDRIs de iluminação e texturas de alta qualidade.
       c. Sketchfab: Use para modelos realistas específicos.
       d. AmbientCG: Use para buscas extensas de materiais PBR.
       e. Scripting: Apenas se não houver asset pronto adequado.

    3. WORKFLOW DE IMPRESSÃO 3D:
       - Defina dimensões exatas com set_exact_dimensions().
       - Verifique erros com check_mesh_integrity().
       - Repare se necessário com auto_repair_mesh().
       - Organize no bed com auto_layout_for_printing().

    4. WORKFLOW DE PRODUTO/ESTÚDIO:
       - Use setup_product_studio() para iluminação profissional instantânea.
       - Configure a câmera focando no produto com setup_camera().
       - Gere renders consistentes com render_catalog_angles().
    """


# Main execution
def main(host: str | None = None, port: int | None = None):
    """Run the MCP server"""
    if host:
        os.environ["BLENDER_HOST"] = host
    if port:
        os.environ["BLENDER_PORT"] = str(port)
    configure_logging()
    mcp.run()


if __name__ == "__main__":
    main()
