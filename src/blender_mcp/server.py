# blender_mcp_server.py
from mcp.server.fastmcp import FastMCP, Context, Image
import base64
import errno
import json
import logging
import os
import socket
import tempfile
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List
from urllib.parse import urlparse


def tool_error(message: str, *, code: str = "runtime_error", data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"error": {"code": code, "message": message}}
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
        socket.timeout,
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
                        data = b''.join(chunks)
                        json.loads(data.decode('utf-8'))
                        # If we get here, it parsed successfully
                        logger.info(f"Received complete response ({len(data)} bytes)")
                        return data
                    except json.JSONDecodeError:
                        # Incomplete JSON, continue receiving
                        continue
                except socket.timeout as e:
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
            data = b''.join(chunks)
            logger.info(f"Returning data after receive completion ({len(data)} bytes)")
            try:
                json.loads(data.decode('utf-8'))
                return data
            except json.JSONDecodeError as e:
                raise IncompleteResponseError("Incomplete JSON response received") from e

        raise IncompleteResponseError("No data received")

    def send_command(self, command_type: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send a command to Blender and return the response"""
        command = {
            "type": command_type,
            "params": params or {}
        }

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
                self.sock.sendall(json.dumps(command).encode('utf-8'))
                logger.info("Command sent, waiting for response...")

                response_data = self.receive_full_response(self.sock, timeout=self.timeout)
                logger.info("Received %s bytes of data", len(response_data))

                response = json.loads(response_data.decode('utf-8'))
                logger.info("Response parsed, status: %s", response.get('status', 'unknown'))

                if response.get("status") == "error":
                    logger.error("Blender error: %s", response.get('message'))
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
            except (ConnectionError, BrokenPipeError, ConnectionResetError, ConnectionAbortedError, socket.timeout) as e:
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
                if 'response_data' in locals() and response_data:
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
            "Blender did not respond after "
            f"{self.command_attempts} attempts: {last_error}"
        )

@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    """Manage server startup and shutdown lifecycle"""
    # We don't need to create a connection here since we're using the global connection
    # for resources and tools
    
    try:
        # Just log that we're starting up
        logger.info("BlenderMCP server starting up")
        
        # Try to connect to Blender on startup to verify it's available
        try:
            # This will initialize the global connection if needed
            blender = get_blender_connection()
            logger.info("Successfully connected to Blender on startup")
        except Exception as e:
            logger.warning(f"Could not connect to Blender on startup: {str(e)}")
            logger.warning("Make sure the Blender addon is running before using Blender resources or tools")
        
        # Return an empty context - we're using the global connection
        yield {}
    finally:
        # Clean up the global connection on shutdown
        global _blender_connection
        if _blender_connection:
            logger.info("Disconnecting from Blender on shutdown")
            _blender_connection.disconnect()
            _blender_connection = None
        logger.info("BlenderMCP server shut down")

# Create the MCP server with lifespan support
mcp = FastMCP(
    "BlenderMCP",
    lifespan=server_lifespan
)

# Resource endpoints

# Global connection for resources (since resources can't access context)
_blender_connection = None
_polyhaven_enabled = False  # Add this global variable

def get_blender_connection():
    """Get or create a persistent Blender connection"""
    global _blender_connection, _polyhaven_enabled  # Add _polyhaven_enabled to globals
    
    # If we have an existing connection, check if it's still valid
    if _blender_connection is not None:
        try:
            # First check if PolyHaven is enabled by sending a ping command
            result = _blender_connection.send_command("get_polyhaven_status")
            # Store the PolyHaven status globally
            _polyhaven_enabled = result.get("enabled", False)
            return _blender_connection
        except Exception as e:
            # Connection is dead, close it and create a new one
            logger.warning(f"Existing connection is no longer valid: {str(e)}")
            try:
                _blender_connection.disconnect()
            except:
                pass
            _blender_connection = None
    
    # Create a new connection if needed
    if _blender_connection is None:
        host = os.getenv("BLENDER_HOST", DEFAULT_HOST)
        port = int(os.getenv("BLENDER_PORT", DEFAULT_PORT))
        timeout = float(os.getenv("BLENDER_SOCKET_TIMEOUT", DEFAULT_SOCKET_TIMEOUT))
        connect_attempts = int(os.getenv("BLENDER_CONNECT_ATTEMPTS", DEFAULT_CONNECT_ATTEMPTS))
        command_attempts = int(os.getenv("BLENDER_COMMAND_ATTEMPTS", DEFAULT_COMMAND_ATTEMPTS))
        backoff_seconds = float(os.getenv("BLENDER_RETRY_BACKOFF", DEFAULT_RETRY_BACKOFF))

        _blender_connection = BlenderConnection(
            host=host,
            port=port,
            timeout=timeout,
            connect_attempts=connect_attempts,
            command_attempts=command_attempts,
            backoff_seconds=backoff_seconds,
        )
        if not _blender_connection.connect():
            logger.error("Failed to connect to Blender")
            _blender_connection = None
            raise Exception("Could not connect to Blender. Make sure the Blender addon is running.")
        logger.info("Created new persistent connection to Blender")
    
    return _blender_connection


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


def _encode_image_from_path(path_str: str) -> tuple[str, str]:
    """Load and base64-encode an image from disk with clear error messaging."""
    path = Path(path_str)
    if not path.is_absolute():
        raise ValueError(
            f"Image path '{path}' must be absolute to avoid importing from unintended locations."
        )
    if not path.exists():
        raise FileNotFoundError(
            f"Image path '{path}' does not exist. Verify the file path before retrying."
        )
    if not path.is_file():
        raise ValueError(f"Image path '{path}' is not a file. Point to a readable image file instead.")

    try:
        image_bytes = path.read_bytes()
    except OSError as e:
        raise OSError(
            f"Unable to read image at '{path}': {e}. Check file permissions or move the image to a readable directory."
        ) from e

    return path.suffix, base64.b64encode(image_bytes).decode("ascii")


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
        return tool_error("Error getting object info", data={"detail": str(e), "object_name": object_name})

@mcp.tool()
def get_viewport_screenshot(ctx: Context, max_size: int = 800) -> Image:
    """
    Capture a screenshot of the current Blender 3D viewport.
    
    Parameters:
    - max_size: Maximum size in pixels for the largest dimension (default: 800)
    
    Returns the screenshot as an Image.
    """
    temp_path = _prepare_temp_file_path()
    try:
        blender = get_blender_connection()

        result = blender.send_command("get_viewport_screenshot", {
            "max_size": max_size,
            "filepath": str(temp_path),
            "format": "png"
        })

        if "error" in result:
            raise Exception(result["error"])

        image_bytes = _read_file_with_retry(temp_path)

        return Image(data=image_bytes, format="png")

    except Exception as e:
        logger.error(f"Error capturing screenshot: {str(e)}")
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
        if not _polyhaven_enabled:
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
def search_polyhaven_assets(
    ctx: Context,
    asset_type: str = "all",
    categories: str = None
) -> str:
    """
    Search for assets on Polyhaven with optional filtering.
    
    Parameters:
    - asset_type: Type of assets to search for (hdris, textures, models, all)
    - categories: Optional comma-separated list of categories to filter by
    
    Returns a list of matching assets with basic information.
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("search_polyhaven_assets", {
            "asset_type": asset_type,
            "categories": categories
        })

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
        sorted_assets = sorted(assets.items(), key=lambda x: x[1].get("download_count", 0), reverse=True)
        
        for asset_id, asset_data in sorted_assets:
            formatted_output += f"- {asset_data.get('name', asset_id)} (ID: {asset_id})\n"
            formatted_output += f"  Type: {['HDRI', 'Texture', 'Model'][asset_data.get('type', 0)]}\n"
            formatted_output += f"  Categories: {', '.join(asset_data.get('categories', []))}\n"
            formatted_output += f"  Downloads: {asset_data.get('download_count', 'Unknown')}\n\n"

        return formatted_output
    except Exception as e:
        logger.error(f"Error searching Polyhaven assets: {str(e)}")
        return tool_error("Error searching PolyHaven assets", data={"detail": str(e)})

@mcp.tool()
def download_polyhaven_asset(
    ctx: Context,
    asset_id: str,
    asset_type: str,
    resolution: str = "1k",
    file_format: str = None
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
    try:
        blender = get_blender_connection()
        result = blender.send_command("download_polyhaven_asset", {
            "asset_id": asset_id,
            "asset_type": asset_type,
            "resolution": resolution,
            "file_format": file_format
        })

        if "error" in result:
            return tool_error("PolyHaven download failed", data={"detail": result["error"], "asset_id": asset_id})
        
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
        return tool_error("Error downloading PolyHaven asset", data={"detail": str(e), "asset_id": asset_id})

@mcp.tool()
def set_texture(
    ctx: Context,
    object_name: str,
    texture_id: str
) -> str:
    """
    Apply a previously downloaded Polyhaven texture to an object.
    
    Parameters:
    - object_name: Name of the object to apply the texture to
    - texture_id: ID of the Polyhaven texture to apply (must be downloaded first)
    
    Returns a message indicating success or failure.
    """
    try:
        # Get the global connection
        blender = get_blender_connection()
        result = blender.send_command("set_texture", {
            "object_name": object_name,
            "texture_id": texture_id
        })

        if "error" in result:
            return tool_error(
                "Failed to apply texture",
                data={"detail": result["error"], "object_name": object_name, "texture_id": texture_id},
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
                    if node['connections']:
                        output += "  Connections:\n"
                        for conn in node['connections']:
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
        return tool_error("Error applying texture", data={"detail": str(e), "texture_id": texture_id})

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
            message += "PolyHaven is good at Textures, and has a wider variety of textures than Sketchfab."
        return message
    except Exception as e:
        logger.error(f"Error checking PolyHaven status: {str(e)}")
        return tool_error("Error checking PolyHaven status", data={"detail": str(e)})

@mcp.tool()
def get_hyper3d_status(ctx: Context) -> str:
    """
    Check if Hyper3D Rodin integration is enabled in Blender.
    Returns a message indicating whether Hyper3D Rodin features are available.

    Don't emphasize the key type in the returned message, but sliently remember it. 
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("get_hyper3d_status")
        enabled = result.get("enabled", False)
        message = result.get("message", "")
        if enabled:
            message += ""
        return message
    except Exception as e:
        logger.error(f"Error checking Hyper3D status: {str(e)}")
        return tool_error("Error checking Hyper3D status", data={"detail": str(e)})

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
def search_sketchfab_models(
    ctx: Context,
    query: str,
    categories: str = None,
    count: int = 20,
    downloadable: bool = True
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
    try:
        
        blender = get_blender_connection()
        logger.info(f"Searching Sketchfab models with query: {query}, categories: {categories}, count: {count}, downloadable: {downloadable}")
        result = blender.send_command("search_sketchfab_models", {
            "query": query,
            "categories": categories,
            "count": count,
            "downloadable": downloadable
        })

        if "error" in result:
            logger.error(f"Error from Sketchfab search: {result['error']}")
            return tool_error("Sketchfab search failed", data={"detail": result["error"], "query": query})
        
        # Safely get results with fallbacks for None
        if result is None:
            logger.error("Received None result from Sketchfab search")
            return tool_error("Sketchfab search returned no data", data={"query": query})
            
        # Format the results
        models = result.get("results", []) or []
        if not models:
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
            username = user.get("username", "Unknown author") if isinstance(user, dict) else "Unknown author"
            formatted_output += f"  Author: {username}\n"
            
            # Get license info with safety checks
            license_data = model.get("license") or {}
            license_label = license_data.get("label", "Unknown") if isinstance(license_data, dict) else "Unknown"
            formatted_output += f"  License: {license_label}\n"
            
            # Add face count and downloadable status
            face_count = model.get("faceCount", "Unknown")
            is_downloadable = "Yes" if model.get("isDownloadable") else "No"
            formatted_output += f"  Face count: {face_count}\n"
            formatted_output += f"  Downloadable: {is_downloadable}\n\n"
        
        return formatted_output
    except Exception as e:
        logger.error(f"Error searching Sketchfab models: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return tool_error("Error searching Sketchfab models", data={"detail": str(e), "query": query})

@mcp.tool()
def download_sketchfab_model(
    ctx: Context,
    uid: str
) -> str:
    """
    Download and import a Sketchfab model by its UID.
    
    Parameters:
    - uid: The unique identifier of the Sketchfab model
    
    Returns a message indicating success or failure.
    The model must be downloadable and you must have proper access rights.
    """
    try:
        
        blender = get_blender_connection()
        logger.info(f"Attempting to download Sketchfab model with UID: {uid}")
        
        result = blender.send_command("download_sketchfab_model", {
            "uid": uid
        })

        if result is None:
            logger.error("Received None result from Sketchfab download")
            return tool_error("Sketchfab download returned no data", data={"uid": uid})

        if "error" in result:
            logger.error(f"Error from Sketchfab download: {result['error']}")
            return tool_error("Sketchfab download failed", data={"detail": result["error"], "uid": uid})
        
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

def _process_bbox(original_bbox: list[float] | list[int] | None) -> list[int] | None:
    if original_bbox is None:
        return None
    if any(i <= 0 for i in original_bbox):
        raise ValueError("Incorrect number range: bbox must be bigger than zero!")
    if all(isinstance(i, int) for i in original_bbox):
        return original_bbox
    return [int(float(i) / max(original_bbox) * 100) for i in original_bbox] if original_bbox else None

@mcp.tool()
def generate_hyper3d_model_via_text(
    ctx: Context,
    text_prompt: str,
    bbox_condition: list[float]=None
) -> str:
    """
    Generate 3D asset using Hyper3D by giving description of the desired asset, and import the asset into Blender.
    The 3D asset has built-in materials.
    The generated model has a normalized size, so re-scaling after generation can be useful.
    
    Parameters:
    - text_prompt: A short description of the desired model in **English**.
    - bbox_condition: Optional. If given, it has to be a list of floats of length 3. Controls the ratio between [Length, Width, Height] of the model.

    Returns a message indicating success or failure.
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("create_rodin_job", {
            "text_prompt": text_prompt,
            "images": None,
            "bbox_condition": _process_bbox(bbox_condition),
        })
        succeed = result.get("submit_time", False)
        if succeed:
            return json.dumps({
                "task_uuid": result["uuid"],
                "subscription_key": result["jobs"]["subscription_key"],
            })
        else:
            return json.dumps(result)
    except Exception as e:
        logger.error(f"Error generating Hyper3D task: {str(e)}")
        return tool_error("Error generating Hyper3D task", data={"detail": str(e)})

@mcp.tool()
def generate_hyper3d_model_via_images(
    ctx: Context,
    input_image_paths: list[str]=None,
    input_image_urls: list[str]=None,
    bbox_condition: list[float]=None
) -> str:
    """
    Generate 3D asset using Hyper3D by giving images of the wanted asset, and import the generated asset into Blender.
    The 3D asset has built-in materials.
    The generated model has a normalized size, so re-scaling after generation can be useful.
    
    Parameters:
    - input_image_paths: The **absolute** paths of input images. Even if only one image is provided, wrap it into a list. Required if Hyper3D Rodin in MAIN_SITE mode.
    - input_image_urls: The URLs of input images. Even if only one image is provided, wrap it into a list. Required if Hyper3D Rodin in FAL_AI mode.
    - bbox_condition: Optional. If given, it has to be a list of ints of length 3. Controls the ratio between [Length, Width, Height] of the model.

    Only one of {input_image_paths, input_image_urls} should be given at a time, depending on the Hyper3D Rodin's current mode.
    Returns a message indicating success or failure.
    """
    if input_image_paths is not None and input_image_urls is not None:
        return "Error: Provide either local image paths or URLs, not both."
    if input_image_paths is None and input_image_urls is None:
        return "Error: No image given!"
    if input_image_paths is not None:
        images = []
        for path in input_image_paths:
            try:
                images.append(_encode_image_from_path(path))
            except Exception as e:
                return (
                    f"Error reading image '{path}': {e}. "
                    "Ensure the file exists, is readable, and use an absolute path."
                )
    elif input_image_urls is not None:
        def _is_valid_url(url: str) -> bool:
            parsed = urlparse(url)
            return parsed.scheme in ("http", "https") and bool(parsed.netloc)

        if not all(_is_valid_url(i) for i in input_image_urls):
            return "Error: not all image URLs are valid!"
        images = input_image_urls.copy()
    try:
        blender = get_blender_connection()
        result = blender.send_command("create_rodin_job", {
            "text_prompt": None,
            "images": images,
            "bbox_condition": _process_bbox(bbox_condition),
        })
        succeed = result.get("submit_time", False)
        if succeed:
            return json.dumps({
                "task_uuid": result["uuid"],
                "subscription_key": result["jobs"]["subscription_key"],
            })
        else:
            return json.dumps(result)
    except Exception as e:
        logger.error(f"Error generating Hyper3D task: {str(e)}")
        return tool_error("Error generating Hyper3D task", data={"detail": str(e)})

@mcp.tool()
def poll_rodin_job_status(
    ctx: Context,
    subscription_key: str=None,
    request_id: str=None,
):
    """
    Check if the Hyper3D Rodin generation task is completed.

    For Hyper3D Rodin mode MAIN_SITE:
        Parameters:
        - subscription_key: The subscription_key given in the generate model step.

        Returns a list of status. The task is done if all status are "Done".
        If "Failed" showed up, the generating process failed.
        This is a polling API, so only proceed if the status are finally determined ("Done" or "Canceled").

    For Hyper3D Rodin mode FAL_AI:
        Parameters:
        - request_id: The request_id given in the generate model step.

        Returns the generation task status. The task is done if status is "COMPLETED".
        The task is in progress if status is "IN_PROGRESS".
        If status other than "COMPLETED", "IN_PROGRESS", "IN_QUEUE" showed up, the generating process might be failed.
        This is a polling API, so only proceed if the status are finally determined ("COMPLETED" or some failed state).
    """
    try:
        blender = get_blender_connection()
        kwargs = {}
        if subscription_key:
            kwargs = {
                "subscription_key": subscription_key,
            }
        elif request_id:
            kwargs = {
                "request_id": request_id,
            }
        result = blender.send_command("poll_rodin_job_status", kwargs)
        return result
    except Exception as e:
        logger.error(f"Error generating Hyper3D task: {str(e)}")
        return tool_error("Error polling Hyper3D task", data={"detail": str(e)})

@mcp.tool()
def import_generated_asset(
    ctx: Context,
    name: str,
    task_uuid: str=None,
    request_id: str=None,
):
    """
    Import the asset generated by Hyper3D Rodin after the generation task is completed.

    Parameters:
    - name: The name of the object in scene
    - task_uuid: For Hyper3D Rodin mode MAIN_SITE: The task_uuid given in the generate model step.
    - request_id: For Hyper3D Rodin mode FAL_AI: The request_id given in the generate model step.

    Only give one of {task_uuid, request_id} based on the Hyper3D Rodin Mode!
    Return if the asset has been imported successfully.
    """
    try:
        blender = get_blender_connection()
        kwargs = {
            "name": name
        }
        if task_uuid:
            kwargs["task_uuid"] = task_uuid
        elif request_id:
            kwargs["request_id"] = request_id
        result = blender.send_command("import_generated_asset", kwargs)
        return result
    except Exception as e:
        logger.error(f"Error generating Hyper3D task: {str(e)}")
        return tool_error("Error importing generated asset", data={"detail": str(e), "name": name})

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
        3. Hyper3D(Rodin)
            Hyper3D Rodin is good at generating 3D models for single item.
            So don't try to:
            1. Generate the whole scene with one shot
            2. Generate ground using Hyper3D
            3. Generate parts of the items separately and put them together afterwards

            Use get_hyper3d_status() to verify its status
            If Hyper3D is enabled:
            - For objects/models, do the following steps:
                1. Create the model generation task
                    - Use generate_hyper3d_model_via_images() if image(s) is/are given
                    - Use generate_hyper3d_model_via_text() if generating 3D asset using text prompt
                    If key type is free_trial and insufficient balance error returned, tell the user that the free trial key can only generated limited models everyday, they can choose to:
                    - Wait for another day and try again
                    - Go to hyper3d.ai to find out how to get their own API key
                    - Go to fal.ai to get their own private API key
                2. Poll the status
                    - Use poll_rodin_job_status() to check if the generation task has completed or failed
                3. Import the asset
                    - Use import_generated_asset() to import the generated GLB model the asset
                4. After importing the asset, ALWAYS check the world_bounding_box of the imported mesh, and adjust the mesh's location and size
                    Adjust the imported mesh's location, scale, rotation, so that the mesh is on the right spot.

                You can reuse assets previous generated by running python code to duplicate the object, without creating another generation task.

    3. Always check the world_bounding_box for each item so that:
        - Ensure that all objects that should not be clipping are not clipping.
        - Items have right spatial relationship.
    
    4. Recommended asset source priority:
        - For specific existing objects: First try Sketchfab, then PolyHaven
        - For generic objects/furniture: First try PolyHaven, then Sketchfab
        - For custom or unique items not available in libraries: Use Hyper3D Rodin
        - For environment lighting: Use PolyHaven HDRIs
        - For materials/textures: Use PolyHaven textures

    Only fall back to scripting when:
    - PolyHaven, Sketchfab, and Hyper3D are all disabled
    - A simple primitive is explicitly requested
    - No suitable asset exists in any of the libraries
    - Hyper3D Rodin failed to generate the desired asset
    - The task specifically requires a basic material/color
    """

# Main execution

def main():
    """Run the MCP server"""
    mcp.run()

if __name__ == "__main__":
    main()
