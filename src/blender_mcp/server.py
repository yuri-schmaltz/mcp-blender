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
) -> dict[str, Any]:
    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    if data:
        payload["error"]["data"] = data
    return payload


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
            "Blender did not respond after " f"{self.command_attempts} attempts: {last_error}"
        )


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """Manage server startup and shutdown lifecycle"""
    # We don't need to create a connection here since we're using the global connection
    # for resources and tools

    try:
        # Just log that we're starting up
        logger.info("BlenderMCP server starting up")

        # Try to connect to Blender on startup to verify it's available
        try:
            # This will initialize the global connection if needed
            get_blender_connection()
            logger.info("Successfully connected to Blender on startup")
        except Exception as e:
            logger.warning(f"Could not connect to Blender on startup: {str(e)}")
            logger.warning(
                "Make sure the Blender addon is running before using Blender resources or tools"
            )

        # Return an empty context - we're using the global connection
        yield {}
    finally:
        # Clean up persistent connection on shutdown.
        connection = _connection_state.get_connection()
        if connection:
            logger.info("Disconnecting from Blender on shutdown")
            connection.disconnect()
            _connection_state.clear()
        logger.info("BlenderMCP server shut down")


# Create the MCP server with lifespan support
mcp = FastMCP("BlenderMCP", lifespan=server_lifespan)

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
    existing_connection = _connection_state.get_connection()
    # If we have an existing connection, check if it's still valid.
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

    # Double-check after potential concurrent creation.
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

    existing_connection = _connection_state.get_connection()
    if existing_connection is not None:
        new_connection.disconnect()
        return existing_connection

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

    assert last_error is not None
    raise last_error


@mcp.tool()
def get_scene_info(ctx: Context) -> str:
    """Get detailed information about the current Blender scene"""
    try:
        blender = get_blender_connection()
        result = blender.send_command("get_scene_info")

        # Just return the JSON representation of what Blender sent us
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting scene info from Blender: {str(e)}")
        return tool_error("Error getting scene info", data={"detail": str(e)})


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


@mcp.prompt()
def asset_creation_strategy() -> str:
    """Defines the preferred strategy for creating assets in Blender"""
    return """When creating 3D content in Blender, always start by checking if integrations are available:

    0. Before anything, always check the scene from get_scene_info()
    1. First use the following tools to verify if the following integrations are enabled:
        1. PolyHaven
            Use get_polyhaven_status() to verify its status
            If PolyHaven is enabled:
            - For objects/models: Use download_polyhaven_asset() with asset_type="models"
            - For materials/textures: Use download_polyhaven_asset() with asset_type="textures"
            - For environment lighting: Use download_polyhaven_asset() with asset_type="hdris"
        2. Sketchfab
            Sketchfab is good at Realistic models, and has a wider variety of models than PolyHaven.
            Use get_sketchfab_status() to verify its status
            If Sketchfab is enabled:
            - For objects/models: First search using search_sketchfab_models() with your query
            - Then download specific models using download_sketchfab_model() with the UID
            - Note that only downloadable models can be accessed, and API key must be properly configured
            - Sketchfab has a wider variety of models than PolyHaven, especially for specific subjects

    2. Always check the world_bounding_box for each item so that:
        - Ensure that all objects that should not be clipping are not clipping.
        - Items have right spatial relationship.

    3. Recommended asset source priority:
        - For specific existing objects: First try Sketchfab, then PolyHaven
        - For generic objects/furniture: First try PolyHaven, then Sketchfab
        - For environment lighting: Use PolyHaven HDRIs
        - For materials/textures: Use PolyHaven textures

    Only fall back to scripting when:
    - PolyHaven and Sketchfab are disabled
    - A simple primitive is explicitly requested
    - No suitable asset exists in any of the libraries
    - The task specifically requires a basic material/color
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

