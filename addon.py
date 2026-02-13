# Code created by Siddharth Ahuja: www.github.com/ahujasid © 2025

import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import zipfile
from contextlib import redirect_stdout, suppress

import bpy
import mathutils
import requests
from bpy.props import IntProperty

from addon.server import BlenderMCPServer as SocketBlenderMCPServer

# Import progress tracking for MP-02
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
try:
    from blender_mcp.progress import get_progress_tracker

    PROGRESS_AVAILABLE = True
except ImportError:
    PROGRESS_AVAILABLE = False

    def get_progress_tracker():
        return None


bl_info = {
    "name": "Blender MCP",
    "author": "BlenderMCP",
    "version": (1, 3, 1),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > BlenderMCP",
    "description": "Connect Blender to local LLM clients via MCP",
    "category": "Interface",
}

# Add User-Agent as required by Poly Haven API
REQ_HEADERS = requests.utils.default_headers()
REQ_HEADERS.update({"User-Agent": "blender-mcp"})

# MP-05: Asset cache configuration
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".blender_mcp", "cache")
CACHE_TTL_DAYS = 7  # Cache expires after 7 days


class AssetCache:
    """Persistent cache for downloaded assets (MP-05)."""

    def __init__(self, cache_dir=CACHE_DIR, ttl_days=CACHE_TTL_DAYS):
        self.cache_dir = cache_dir
        self.ttl_seconds = ttl_days * 24 * 3600
        os.makedirs(cache_dir, exist_ok=True)

    def _get_cache_path(self, asset_id: str, asset_type: str, resolution: str = "") -> str:
        """Generate cache file path from asset identifiers."""
        import hashlib

        cache_key = f"{asset_id}_{asset_type}_{resolution}"
        cache_hash = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, f"{cache_hash}.cache")

    def get(self, asset_id: str, asset_type: str, resolution: str = "") -> str | None:
        """Retrieve cached asset path if valid, None otherwise."""
        cache_path = self._get_cache_path(asset_id, asset_type, resolution)

        if not os.path.exists(cache_path):
            return None

        # Check if cache is expired
        file_age = time.time() - os.path.getmtime(cache_path)
        if file_age > self.ttl_seconds:
            try:
                os.remove(cache_path)
            except OSError:
                pass
            return None

        return cache_path

    def put(self, asset_id: str, asset_type: str, source_path: str, resolution: str = "") -> str:
        """Store asset in cache and return cache path."""
        cache_path = self._get_cache_path(asset_id, asset_type, resolution)

        try:
            shutil.copy2(source_path, cache_path)
            return cache_path
        except Exception as e:
            print(f"Failed to cache asset: {e}")
            return source_path

    def clear(self) -> int:
        """Clear all cached assets. Returns number of files deleted."""
        deleted = 0
        try:
            for filename in os.listdir(self.cache_dir):
                filepath = os.path.join(self.cache_dir, filename)
                if os.path.isfile(filepath):
                    os.remove(filepath)
                    deleted += 1
        except Exception as e:
            print(f"Error clearing cache: {e}")
        return deleted

    def get_cache_size(self) -> tuple[int, int]:
        """Get cache size in bytes and number of files."""
        total_size = 0
        file_count = 0
        try:
            for filename in os.listdir(self.cache_dir):
                filepath = os.path.join(self.cache_dir, filename)
                if os.path.isfile(filepath):
                    total_size += os.path.getsize(filepath)
                    file_count += 1
        except OSError:
            pass
        return total_size, file_count


# Global cache instance
_asset_cache = AssetCache()


def _project_root() -> str:
    """Return repository root path based on addon.py location."""
    return os.path.dirname(os.path.abspath(__file__))


def _run_command(command: list[str], cwd: str) -> tuple[int, str]:
    """Run command and return exit code + combined output."""
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=1200,
            check=False,
        )
    except FileNotFoundError:
        return 127, f"Command not found: {command[0]}"
    except Exception as exc:  # pragma: no cover - defensive path
        return 1, str(exc)

    output = (completed.stdout or "").strip()
    err = (completed.stderr or "").strip()
    combined = "\n".join(part for part in [output, err] if part)
    return completed.returncode, combined


def _mcp_client_config_snippet(client: str, host: str, port: int) -> str:
    """Generate stdio config snippets for MCP-compatible clients."""
    args = ["run", "blender-mcp", "--host", host, "--port", str(port)]
    config = {"mcpServers": {"blender": {"command": "uv", "args": args}}}
    if client == "claude":
        return json.dumps(config, indent=2)
    if client == "cursor":
        return json.dumps(config, indent=2)
    if client == "lm_studio":
        return json.dumps(config, indent=2)
    if client == "ollama":
        return (
            "Use this in your MCP-capable Ollama client (Continue/Open WebUI/etc):\n"
            + json.dumps(config, indent=2)
        )
    return json.dumps(config, indent=2)


def _update_action_status(scene, action: str, ok: bool, details: str = "") -> None:
    """Persist last action result in scene properties for UI visibility."""
    scene.blendermcp_last_action = action
    scene.blendermcp_last_action_ok = ok
    scene.blendermcp_last_action_details = details[:500]
    scene.blendermcp_last_action_at = time.strftime("%Y-%m-%d %H:%M:%S")


def _logs_path() -> str:
    """Resolve current log path from env or default value."""
    log_file = os.getenv("BLENDER_MCP_LOG_FILE", "blender_mcp.log")
    if os.path.isabs(log_file):
        return log_file
    return os.path.join(_project_root(), log_file)


def _open_in_system(path: str) -> None:
    """Open path using platform default app/file manager."""
    if os.name == "nt":
        os.startfile(path)
        return
    if platform.system() == "Darwin":
        subprocess.Popen(["open", path])
        return
    subprocess.Popen(["xdg-open", path])


class BlenderMCPServer(SocketBlenderMCPServer):
    def __init__(self, host="localhost", port=9876):
        super().__init__(host=host, port=port)
        self.command_executor = self._execute_command_internal

    def _execute_command_internal(self, command):
        """Internal command execution with proper context"""
        cmd_type = command.get("type")
        params = command.get("params", {})

        # Add a handler for checking PolyHaven status
        if cmd_type == "get_polyhaven_status":
            return {"status": "success", "result": self.get_polyhaven_status()}

        # Base handlers that are always available
        handlers = {
            "get_scene_info": self.get_scene_info,
            "get_object_info": self.get_object_info,
            "get_viewport_screenshot": self.get_viewport_screenshot,
            "execute_code": self.execute_code,
            "get_polyhaven_status": self.get_polyhaven_status,
            "get_sketchfab_status": self.get_sketchfab_status,
        }

        # Add Polyhaven handlers only if enabled
        if bpy.context.scene.blendermcp_use_polyhaven:
            polyhaven_handlers = {
                "get_polyhaven_categories": self.get_polyhaven_categories,
                "search_polyhaven_assets": self.search_polyhaven_assets,
                "download_polyhaven_asset": self.download_polyhaven_asset,
                "set_texture": self.set_texture,
            }
            handlers.update(polyhaven_handlers)

        # Add Sketchfab handlers only if enabled
        if bpy.context.scene.blendermcp_use_sketchfab:
            sketchfab_handlers = {
                "search_sketchfab_models": self.search_sketchfab_models,
                "download_sketchfab_model": self.download_sketchfab_model,
            }
            handlers.update(sketchfab_handlers)

        handler = handlers.get(cmd_type)
        if handler:
            try:
                print(f"Executing handler for {cmd_type}")
                result = handler(**params)
                print("Handler execution complete")
                return {"status": "success", "result": result}
            except Exception as e:
                print(f"Error in handler: {str(e)}")
                traceback.print_exc()
                return {"status": "error", "message": str(e)}
        else:
            return {"status": "error", "message": f"Unknown command type: {cmd_type}"}

    def get_scene_info(self):
        """Get information about the current Blender scene"""
        try:
            print("Getting scene info...")
            # Simplify the scene info to reduce data size
            scene_info = {
                "name": bpy.context.scene.name,
                "object_count": len(bpy.context.scene.objects),
                "objects": [],
                "materials_count": len(bpy.data.materials),
            }

            # Collect minimal object information (limit to first 10 objects)
            for i, obj in enumerate(bpy.context.scene.objects):
                if i >= 10:  # Reduced from 20 to 10
                    break

                obj_info = {
                    "name": obj.name,
                    "type": obj.type,
                    # Only include basic location data
                    "location": [
                        round(float(obj.location.x), 2),
                        round(float(obj.location.y), 2),
                        round(float(obj.location.z), 2),
                    ],
                }
                scene_info["objects"].append(obj_info)

            print(f"Scene info collected: {len(scene_info['objects'])} objects")
            return scene_info
        except Exception as e:
            print(f"Error in get_scene_info: {str(e)}")
            traceback.print_exc()
            return {"error": str(e)}

    @staticmethod
    def _get_aabb(obj):
        """Returns the world-space axis-aligned bounding box (AABB) of an object."""
        if obj.type != "MESH":
            raise TypeError("Object must be a mesh")

        # Get the bounding box corners in local space
        local_bbox_corners = [mathutils.Vector(corner) for corner in obj.bound_box]

        # Convert to world coordinates
        world_bbox_corners = [obj.matrix_world @ corner for corner in local_bbox_corners]

        # Compute axis-aligned min/max coordinates
        min_corner = mathutils.Vector(map(min, zip(*world_bbox_corners)))
        max_corner = mathutils.Vector(map(max, zip(*world_bbox_corners)))

        return [[*min_corner], [*max_corner]]

    def get_object_info(self, name):
        """Get detailed information about a specific object"""
        obj = bpy.data.objects.get(name)
        if not obj:
            raise ValueError(f"Object not found: {name}")

        # Basic object info
        obj_info = {
            "name": obj.name,
            "type": obj.type,
            "location": [obj.location.x, obj.location.y, obj.location.z],
            "rotation": [obj.rotation_euler.x, obj.rotation_euler.y, obj.rotation_euler.z],
            "scale": [obj.scale.x, obj.scale.y, obj.scale.z],
            "visible": obj.visible_get(),
            "materials": [],
        }

        if obj.type == "MESH":
            bounding_box = self._get_aabb(obj)
            obj_info["world_bounding_box"] = bounding_box

        # Add material slots
        for slot in obj.material_slots:
            if slot.material:
                obj_info["materials"].append(slot.material.name)

        # Add mesh data if applicable
        if obj.type == "MESH" and obj.data:
            mesh = obj.data
            obj_info["mesh"] = {
                "vertices": len(mesh.vertices),
                "edges": len(mesh.edges),
                "polygons": len(mesh.polygons),
            }

        return obj_info

    def get_viewport_screenshot(self, max_size=800, filepath=None, format="png"):
        """
        Capture a screenshot of the current 3D viewport and save it to the specified path.

        Parameters:
        - max_size: Maximum size in pixels for the largest dimension of the image
        - filepath: Path where to save the screenshot file
        - format: Image format (png, jpg, etc.)

        Returns success/error status
        """
        try:
            if not filepath:
                return {"error": "No filepath provided"}

            # Find the active 3D viewport
            area = None
            for a in bpy.context.screen.areas:
                if a.type == "VIEW_3D":
                    area = a
                    break

            if not area:
                return {"error": "No 3D viewport found"}

            # Take screenshot with proper context override
            with bpy.context.temp_override(area=area):
                bpy.ops.screen.screenshot_area(filepath=filepath)

            # Load and resize if needed
            img = bpy.data.images.load(filepath)
            width, height = img.size

            if max(width, height) > max_size:
                scale = max_size / max(width, height)
                new_width = int(width * scale)
                new_height = int(height * scale)
                img.scale(new_width, new_height)

                # Set format and save
                img.file_format = format.upper()
                img.save()
                width, height = new_width, new_height

            # Cleanup Blender image data
            bpy.data.images.remove(img)

            return {"success": True, "width": width, "height": height, "filepath": filepath}

        except Exception as e:
            return {"error": str(e)}

    def execute_code(self, code):
        """Execute arbitrary Blender Python code"""
        # This is powerful but potentially dangerous - use with caution
        try:
            # Create a local namespace for execution
            namespace = {"bpy": bpy}

            # Capture stdout during execution, and return it as result
            capture_buffer = io.StringIO()
            with redirect_stdout(capture_buffer):
                exec(code, namespace)

            captured_output = capture_buffer.getvalue()
            return {"executed": True, "result": captured_output}
        except Exception as e:
            raise Exception(f"Code execution error: {str(e)}")

    def get_polyhaven_categories(self, asset_type):
        """Get categories for a specific asset type from Polyhaven"""
        try:
            if asset_type not in ["hdris", "textures", "models", "all"]:
                return {
                    "error": f"Invalid asset type: {asset_type}. Must be one of: hdris, textures, models, all"
                }

            response = requests.get(
                f"https://api.polyhaven.com/categories/{asset_type}", headers=REQ_HEADERS
            )
            if response.status_code == 200:
                return {"categories": response.json()}
            else:
                return {"error": f"API request failed with status code {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}

    def search_polyhaven_assets(self, asset_type=None, categories=None):
        """Search for assets from Polyhaven with optional filtering"""
        try:
            url = "https://api.polyhaven.com/assets"
            params = {}

            if asset_type and asset_type != "all":
                if asset_type not in ["hdris", "textures", "models"]:
                    return {
                        "error": f"Invalid asset type: {asset_type}. Must be one of: hdris, textures, models, all"
                    }
                params["type"] = asset_type

            if categories:
                params["categories"] = categories

            response = requests.get(url, params=params, headers=REQ_HEADERS)
            if response.status_code == 200:
                # Limit the response size to avoid overwhelming Blender
                assets = response.json()
                # Return only the first 20 assets to keep response size manageable
                limited_assets = {}
                for i, (key, value) in enumerate(assets.items()):
                    if i >= 20:  # Limit to 20 assets
                        break
                    limited_assets[key] = value

                return {
                    "assets": limited_assets,
                    "total_count": len(assets),
                    "returned_count": len(limited_assets),
                }
            else:
                return {"error": f"API request failed with status code {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}

    def download_polyhaven_asset(self, asset_id, asset_type, resolution="1k", file_format=None):
        try:
            # First get the files information
            files_response = requests.get(
                f"https://api.polyhaven.com/files/{asset_id}", headers=REQ_HEADERS
            )
            if files_response.status_code != 200:
                return {"error": f"Failed to get asset files: {files_response.status_code}"}

            files_data = files_response.json()

            # Handle different asset types
            if asset_type == "hdris":
                # For HDRIs, download the .hdr or .exr file
                if not file_format:
                    file_format = "hdr"  # Default format for HDRIs

                if (
                    "hdri" in files_data
                    and resolution in files_data["hdri"]
                    and file_format in files_data["hdri"][resolution]
                ):
                    file_info = files_data["hdri"][resolution][file_format]
                    file_url = file_info["url"]

                    # For HDRIs, we need to save to a temporary file first
                    # since Blender can't properly load HDR data directly from memory
                    tmp_file = tempfile.NamedTemporaryFile(suffix=f".{file_format}", delete=False)
                    tmp_path = tmp_file.name
                    tmp_file.close()

                    try:
                        # Download the file with progress tracking (MP-02)
                        operation_id = f"polyhaven_hdri_{asset_id}_{resolution}"

                        response = requests.get(file_url, headers=REQ_HEADERS, stream=True)
                        if response.status_code != 200:
                            return {"error": f"Failed to download HDRI: {response.status_code}"}

                        # Get total size and start progress tracking
                        total_size = int(response.headers.get("content-length", 0))
                        downloaded = 0

                        if PROGRESS_AVAILABLE:
                            tracker = get_progress_tracker()
                            if tracker:
                                tracker.start_operation(operation_id, total_size)

                        # Download with streaming and progress updates
                        with open(tmp_path, "wb") as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                                    downloaded += len(chunk)
                                    if PROGRESS_AVAILABLE and tracker:
                                        tracker.update_progress(operation_id, downloaded)

                        if PROGRESS_AVAILABLE and tracker:
                            tracker.complete_operation(operation_id)

                        # Create a new world if none exists
                        if not bpy.data.worlds:
                            bpy.data.worlds.new("World")

                        world = bpy.data.worlds[0]
                        world.use_nodes = True
                        node_tree = world.node_tree

                        # Clear existing nodes
                        for node in node_tree.nodes:
                            node_tree.nodes.remove(node)

                        # Create nodes
                        tex_coord = node_tree.nodes.new(type="ShaderNodeTexCoord")
                        tex_coord.location = (-800, 0)

                        mapping = node_tree.nodes.new(type="ShaderNodeMapping")
                        mapping.location = (-600, 0)

                        # Load the image from the temporary file
                        env_tex = node_tree.nodes.new(type="ShaderNodeTexEnvironment")
                        env_tex.location = (-400, 0)
                        env_tex.image = bpy.data.images.load(tmp_path)

                        # Use a color space that exists in all Blender versions
                        if file_format.lower() == "exr":
                            # Try to use Linear color space for EXR files
                            try:
                                env_tex.image.colorspace_settings.name = "Linear"
                            except Exception:
                                # Fallback to Non-Color if Linear isn't available
                                env_tex.image.colorspace_settings.name = "Non-Color"
                        else:  # hdr
                            # For HDR files, try these options in order
                            for color_space in ["Linear", "Linear Rec.709", "Non-Color"]:
                                try:
                                    env_tex.image.colorspace_settings.name = color_space
                                    break  # Stop if we successfully set a color space
                                except Exception:
                                    continue

                        background = node_tree.nodes.new(type="ShaderNodeBackground")
                        background.location = (-200, 0)

                        output = node_tree.nodes.new(type="ShaderNodeOutputWorld")
                        output.location = (0, 0)

                        # Connect nodes
                        node_tree.links.new(
                            tex_coord.outputs["Generated"], mapping.inputs["Vector"]
                        )
                        node_tree.links.new(mapping.outputs["Vector"], env_tex.inputs["Vector"])
                        node_tree.links.new(env_tex.outputs["Color"], background.inputs["Color"])
                        node_tree.links.new(
                            background.outputs["Background"], output.inputs["Surface"]
                        )

                        # Set as active world
                        bpy.context.scene.world = world

                        return {
                            "success": True,
                            "message": f"HDRI {asset_id} imported successfully",
                            "image_name": env_tex.image.name,
                        }
                    except Exception as e:
                        return {"error": f"Failed to set up HDRI in Blender: {str(e)}"}
                    finally:
                        # CRITICAL: Always cleanup temporary file, even if there was an error
                        try:
                            if os.path.exists(tmp_path):
                                os.unlink(tmp_path)
                        except Exception as cleanup_error:
                            print(
                                f"Warning: Failed to cleanup temp file {tmp_path}: {cleanup_error}"
                            )
                else:
                    return {"error": "Requested resolution or format not available for this HDRI"}

            elif asset_type == "textures":
                if not file_format:
                    file_format = "jpg"  # Default format for textures

                downloaded_maps = {}

                try:
                    for map_type in files_data:
                        if map_type not in ["blend", "gltf"]:  # Skip non-texture files
                            if (
                                resolution in files_data[map_type]
                                and file_format in files_data[map_type][resolution]
                            ):
                                file_info = files_data[map_type][resolution][file_format]
                                file_url = file_info["url"]

                                # Use NamedTemporaryFile to create temp file
                                tmp_file = tempfile.NamedTemporaryFile(
                                    suffix=f".{file_format}", delete=False
                                )
                                tmp_path = tmp_file.name
                                tmp_file.close()

                                try:
                                    # Download the file with progress tracking (MP-02)
                                    operation_id = (
                                        f"polyhaven_tex_{asset_id}_{map_type}_{resolution}"
                                    )

                                    response = requests.get(
                                        file_url, headers=REQ_HEADERS, stream=True
                                    )
                                    if response.status_code == 200:
                                        # Get total size and start progress tracking
                                        total_size = int(response.headers.get("content-length", 0))
                                        downloaded = 0

                                        if PROGRESS_AVAILABLE:
                                            tracker = get_progress_tracker()
                                            if tracker:
                                                tracker.start_operation(operation_id, total_size)

                                        # Download with streaming
                                        with open(tmp_path, "wb") as f:
                                            for chunk in response.iter_content(chunk_size=8192):
                                                if chunk:
                                                    f.write(chunk)
                                                    downloaded += len(chunk)
                                                    if PROGRESS_AVAILABLE and tracker:
                                                        tracker.update_progress(
                                                            operation_id, downloaded
                                                        )

                                        if PROGRESS_AVAILABLE and tracker:
                                            tracker.complete_operation(operation_id)

                                        # Load image from temporary file
                                        image = bpy.data.images.load(tmp_path)
                                        image.name = f"{asset_id}_{map_type}.{file_format}"

                                        # Pack the image into .blend file
                                        image.pack()

                                        # Set color space based on map type
                                        if map_type in ["color", "diffuse", "albedo"]:
                                            try:
                                                image.colorspace_settings.name = "sRGB"
                                            except Exception:
                                                pass
                                        else:
                                            try:
                                                image.colorspace_settings.name = "Non-Color"
                                            except Exception:
                                                pass

                                        downloaded_maps[map_type] = image
                                finally:
                                    # CRITICAL: Always cleanup temporary file
                                    try:
                                        if os.path.exists(tmp_path):
                                            os.unlink(tmp_path)
                                    except Exception as cleanup_error:
                                        print(
                                            f"Warning: Failed to cleanup temp file {tmp_path}: {cleanup_error}"
                                        )

                    if not downloaded_maps:
                        return {
                            "error": "No texture maps found for the requested resolution and format"
                        }

                    # Create a new material with the downloaded textures
                    mat = bpy.data.materials.new(name=asset_id)
                    mat.use_nodes = True
                    nodes = mat.node_tree.nodes
                    links = mat.node_tree.links

                    # Clear default nodes
                    for node in nodes:
                        nodes.remove(node)

                    # Create output node
                    output = nodes.new(type="ShaderNodeOutputMaterial")
                    output.location = (300, 0)

                    # Create principled BSDF node
                    principled = nodes.new(type="ShaderNodeBsdfPrincipled")
                    principled.location = (0, 0)
                    links.new(principled.outputs[0], output.inputs[0])

                    # Add texture nodes based on available maps
                    tex_coord = nodes.new(type="ShaderNodeTexCoord")
                    tex_coord.location = (-800, 0)

                    mapping = nodes.new(type="ShaderNodeMapping")
                    mapping.location = (-600, 0)
                    mapping.vector_type = "TEXTURE"  # Changed from default 'POINT' to 'TEXTURE'
                    links.new(tex_coord.outputs["UV"], mapping.inputs["Vector"])

                    # Position offset for texture nodes
                    x_pos = -400
                    y_pos = 300

                    # Connect different texture maps
                    for map_type, image in downloaded_maps.items():
                        tex_node = nodes.new(type="ShaderNodeTexImage")
                        tex_node.location = (x_pos, y_pos)
                        tex_node.image = image

                        # Set color space based on map type
                        if map_type.lower() in ["color", "diffuse", "albedo"]:
                            try:
                                tex_node.image.colorspace_settings.name = "sRGB"
                            except Exception:
                                pass  # Use default if sRGB not available
                        else:
                            try:
                                tex_node.image.colorspace_settings.name = "Non-Color"
                            except Exception:
                                pass  # Use default if Non-Color not available

                        links.new(mapping.outputs["Vector"], tex_node.inputs["Vector"])

                        # Connect to appropriate input on Principled BSDF
                        if map_type.lower() in ["color", "diffuse", "albedo"]:
                            links.new(tex_node.outputs["Color"], principled.inputs["Base Color"])
                        elif map_type.lower() in ["roughness", "rough"]:
                            links.new(tex_node.outputs["Color"], principled.inputs["Roughness"])
                        elif map_type.lower() in ["metallic", "metalness", "metal"]:
                            links.new(tex_node.outputs["Color"], principled.inputs["Metallic"])
                        elif map_type.lower() in ["normal", "nor"]:
                            # Add normal map node
                            normal_map = nodes.new(type="ShaderNodeNormalMap")
                            normal_map.location = (x_pos + 200, y_pos)
                            links.new(tex_node.outputs["Color"], normal_map.inputs["Color"])
                            links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])
                        elif map_type in ["displacement", "disp", "height"]:
                            # Add displacement node
                            disp_node = nodes.new(type="ShaderNodeDisplacement")
                            disp_node.location = (x_pos + 200, y_pos - 200)
                            links.new(tex_node.outputs["Color"], disp_node.inputs["Height"])
                            links.new(
                                disp_node.outputs["Displacement"], output.inputs["Displacement"]
                            )

                        y_pos -= 250

                    return {
                        "success": True,
                        "message": f"Texture {asset_id} imported as material",
                        "material": mat.name,
                        "maps": list(downloaded_maps.keys()),
                    }

                except Exception as e:
                    return {"error": f"Failed to process textures: {str(e)}"}

            elif asset_type == "models":
                # For models, prefer glTF format if available
                if not file_format:
                    file_format = "gltf"  # Default format for models

                if file_format in files_data and resolution in files_data[file_format]:
                    file_info = files_data[file_format][resolution][file_format]
                    file_url = file_info["url"]

                    # Create a temporary directory to store the model and its dependencies
                    temp_dir = tempfile.mkdtemp()
                    main_file_path = ""

                    try:
                        # Download the main model file
                        main_file_name = file_url.split("/")[-1]
                        main_file_path = os.path.join(temp_dir, main_file_name)

                        response = requests.get(file_url, headers=REQ_HEADERS)
                        if response.status_code != 200:
                            return {"error": f"Failed to download model: {response.status_code}"}

                        with open(main_file_path, "wb") as f:
                            f.write(response.content)

                        # Check for included files and download them
                        if "include" in file_info and file_info["include"]:
                            for include_path, include_info in file_info["include"].items():
                                # Get the URL for the included file - this is the fix
                                include_url = include_info["url"]

                                # Create the directory structure for the included file
                                include_file_path = os.path.join(temp_dir, include_path)
                                os.makedirs(os.path.dirname(include_file_path), exist_ok=True)

                                # Download the included file
                                include_response = requests.get(include_url, headers=REQ_HEADERS)
                                if include_response.status_code == 200:
                                    with open(include_file_path, "wb") as f:
                                        f.write(include_response.content)
                                else:
                                    print(f"Failed to download included file: {include_path}")

                        # Import the model into Blender
                        if file_format == "gltf" or file_format == "glb":
                            bpy.ops.import_scene.gltf(filepath=main_file_path)
                        elif file_format == "fbx":
                            bpy.ops.import_scene.fbx(filepath=main_file_path)
                        elif file_format == "obj":
                            bpy.ops.import_scene.obj(filepath=main_file_path)
                        elif file_format == "blend":
                            # For blend files, we need to append or link
                            with bpy.data.libraries.load(main_file_path, link=False) as (
                                data_from,
                                data_to,
                            ):
                                data_to.objects = data_from.objects

                            # Link the objects to the scene
                            for obj in data_to.objects:
                                if obj is not None:
                                    bpy.context.collection.objects.link(obj)
                        else:
                            return {"error": f"Unsupported model format: {file_format}"}

                        # Get the names of imported objects
                        imported_objects = [obj.name for obj in bpy.context.selected_objects]

                        return {
                            "success": True,
                            "message": f"Model {asset_id} imported successfully",
                            "imported_objects": imported_objects,
                        }
                    except Exception as e:
                        return {"error": f"Failed to import model: {str(e)}"}
                    finally:
                        # Clean up temporary directory
                        with suppress(Exception):
                            shutil.rmtree(temp_dir)
                else:
                    return {"error": "Requested format or resolution not available for this model"}

            else:
                return {"error": f"Unsupported asset type: {asset_type}"}

        except Exception as e:
            return {"error": f"Failed to download asset: {str(e)}"}

    def set_texture(self, object_name, texture_id):
        """Apply a previously downloaded Polyhaven texture to an object by creating a new material"""
        try:
            # Get the object
            obj = bpy.data.objects.get(object_name)
            if not obj:
                return {"error": f"Object not found: {object_name}"}

            # Make sure object can accept materials
            if not hasattr(obj, "data") or not hasattr(obj.data, "materials"):
                return {"error": f"Object {object_name} cannot accept materials"}

            # Find all images related to this texture and ensure they're properly loaded
            texture_images = {}
            for img in bpy.data.images:
                if img.name.startswith(texture_id + "_"):
                    # Extract the map type from the image name
                    map_type = img.name.split("_")[-1].split(".")[0]

                    # Force a reload of the image
                    img.reload()

                    # Ensure proper color space
                    if map_type.lower() in ["color", "diffuse", "albedo"]:
                        try:
                            img.colorspace_settings.name = "sRGB"
                        except Exception:
                            pass
                    else:
                        try:
                            img.colorspace_settings.name = "Non-Color"
                        except Exception:
                            pass

                    # Ensure the image is packed
                    if not img.packed_file:
                        img.pack()

                    texture_images[map_type] = img
                    print(f"Loaded texture map: {map_type} - {img.name}")

                    # Debug info
                    print(f"Image size: {img.size[0]}x{img.size[1]}")
                    print(f"Color space: {img.colorspace_settings.name}")
                    print(f"File format: {img.file_format}")
                    print(f"Is packed: {bool(img.packed_file)}")

            if not texture_images:
                return {
                    "error": f"No texture images found for: {texture_id}. Please download the texture first."
                }

            # Create a new material
            new_mat_name = f"{texture_id}_material_{object_name}"

            # Remove any existing material with this name to avoid conflicts
            existing_mat = bpy.data.materials.get(new_mat_name)
            if existing_mat:
                bpy.data.materials.remove(existing_mat)

            new_mat = bpy.data.materials.new(name=new_mat_name)
            new_mat.use_nodes = True

            # Set up the material nodes
            nodes = new_mat.node_tree.nodes
            links = new_mat.node_tree.links

            # Clear default nodes
            nodes.clear()

            # Create output node
            output = nodes.new(type="ShaderNodeOutputMaterial")
            output.location = (600, 0)

            # Create principled BSDF node
            principled = nodes.new(type="ShaderNodeBsdfPrincipled")
            principled.location = (300, 0)
            links.new(principled.outputs[0], output.inputs[0])

            # Add texture nodes based on available maps
            tex_coord = nodes.new(type="ShaderNodeTexCoord")
            tex_coord.location = (-800, 0)

            mapping = nodes.new(type="ShaderNodeMapping")
            mapping.location = (-600, 0)
            mapping.vector_type = "TEXTURE"  # Changed from default 'POINT' to 'TEXTURE'
            links.new(tex_coord.outputs["UV"], mapping.inputs["Vector"])

            # Position offset for texture nodes
            x_pos = -400
            y_pos = 300

            # Connect different texture maps
            for map_type, image in texture_images.items():
                tex_node = nodes.new(type="ShaderNodeTexImage")
                tex_node.location = (x_pos, y_pos)
                tex_node.image = image

                # Set color space based on map type
                if map_type.lower() in ["color", "diffuse", "albedo"]:
                    try:
                        tex_node.image.colorspace_settings.name = "sRGB"
                    except Exception:
                        pass  # Use default if sRGB not available
                else:
                    try:
                        tex_node.image.colorspace_settings.name = "Non-Color"
                    except Exception:
                        pass  # Use default if Non-Color not available

                links.new(mapping.outputs["Vector"], tex_node.inputs["Vector"])

                # Connect to appropriate input on Principled BSDF
                if map_type.lower() in ["color", "diffuse", "albedo"]:
                    links.new(tex_node.outputs["Color"], principled.inputs["Base Color"])
                elif map_type.lower() in ["roughness", "rough"]:
                    links.new(tex_node.outputs["Color"], principled.inputs["Roughness"])
                elif map_type.lower() in ["metallic", "metalness", "metal"]:
                    links.new(tex_node.outputs["Color"], principled.inputs["Metallic"])
                elif map_type.lower() in ["normal", "nor", "dx", "gl"]:
                    # Add normal map node
                    normal_map = nodes.new(type="ShaderNodeNormalMap")
                    normal_map.location = (x_pos + 200, y_pos)
                    links.new(tex_node.outputs["Color"], normal_map.inputs["Color"])
                    links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])
                elif map_type.lower() in ["displacement", "disp", "height"]:
                    # Add displacement node
                    disp_node = nodes.new(type="ShaderNodeDisplacement")
                    disp_node.location = (x_pos + 200, y_pos - 200)
                    disp_node.inputs["Scale"].default_value = 0.1  # Reduce displacement strength
                    links.new(tex_node.outputs["Color"], disp_node.inputs["Height"])
                    links.new(disp_node.outputs["Displacement"], output.inputs["Displacement"])

                y_pos -= 250

            # Second pass: Connect nodes with proper handling for special cases
            texture_nodes = {}

            # First find all texture nodes and store them by map type
            for node in nodes:
                if node.type == "TEX_IMAGE" and node.image:
                    for map_type, image in texture_images.items():
                        if node.image == image:
                            texture_nodes[map_type] = node
                            break

            # Now connect everything using the nodes instead of images
            # Handle base color (diffuse)
            for map_name in ["color", "diffuse", "albedo"]:
                if map_name in texture_nodes:
                    links.new(
                        texture_nodes[map_name].outputs["Color"], principled.inputs["Base Color"]
                    )
                    print(f"Connected {map_name} to Base Color")
                    break

            # Handle roughness
            for map_name in ["roughness", "rough"]:
                if map_name in texture_nodes:
                    links.new(
                        texture_nodes[map_name].outputs["Color"], principled.inputs["Roughness"]
                    )
                    print(f"Connected {map_name} to Roughness")
                    break

            # Handle metallic
            for map_name in ["metallic", "metalness", "metal"]:
                if map_name in texture_nodes:
                    links.new(
                        texture_nodes[map_name].outputs["Color"], principled.inputs["Metallic"]
                    )
                    print(f"Connected {map_name} to Metallic")
                    break

            # Handle normal maps
            for map_name in ["gl", "dx", "nor"]:
                if map_name in texture_nodes:
                    normal_map_node = nodes.new(type="ShaderNodeNormalMap")
                    normal_map_node.location = (100, 100)
                    links.new(
                        texture_nodes[map_name].outputs["Color"], normal_map_node.inputs["Color"]
                    )
                    links.new(normal_map_node.outputs["Normal"], principled.inputs["Normal"])
                    print(f"Connected {map_name} to Normal")
                    break

            # Handle displacement
            for map_name in ["displacement", "disp", "height"]:
                if map_name in texture_nodes:
                    disp_node = nodes.new(type="ShaderNodeDisplacement")
                    disp_node.location = (300, -200)
                    disp_node.inputs["Scale"].default_value = 0.1  # Reduce displacement strength
                    links.new(texture_nodes[map_name].outputs["Color"], disp_node.inputs["Height"])
                    links.new(disp_node.outputs["Displacement"], output.inputs["Displacement"])
                    print(f"Connected {map_name} to Displacement")
                    break

            # Handle ARM texture (Ambient Occlusion, Roughness, Metallic)
            if "arm" in texture_nodes:
                separate_rgb = nodes.new(type="ShaderNodeSeparateRGB")
                separate_rgb.location = (-200, -100)
                links.new(texture_nodes["arm"].outputs["Color"], separate_rgb.inputs["Image"])

                # Connect Roughness (G) if no dedicated roughness map
                if not any(map_name in texture_nodes for map_name in ["roughness", "rough"]):
                    links.new(separate_rgb.outputs["G"], principled.inputs["Roughness"])
                    print("Connected ARM.G to Roughness")

                # Connect Metallic (B) if no dedicated metallic map
                if not any(
                    map_name in texture_nodes for map_name in ["metallic", "metalness", "metal"]
                ):
                    links.new(separate_rgb.outputs["B"], principled.inputs["Metallic"])
                    print("Connected ARM.B to Metallic")

                # For AO (R channel), multiply with base color if we have one
                base_color_node = None
                for map_name in ["color", "diffuse", "albedo"]:
                    if map_name in texture_nodes:
                        base_color_node = texture_nodes[map_name]
                        break

                if base_color_node:
                    mix_node = nodes.new(type="ShaderNodeMixRGB")
                    mix_node.location = (100, 200)
                    mix_node.blend_type = "MULTIPLY"
                    mix_node.inputs["Fac"].default_value = 0.8  # 80% influence

                    # Disconnect direct connection to base color
                    for link in base_color_node.outputs["Color"].links:
                        if link.to_socket == principled.inputs["Base Color"]:
                            links.remove(link)

                    # Connect through the mix node
                    links.new(base_color_node.outputs["Color"], mix_node.inputs[1])
                    links.new(separate_rgb.outputs["R"], mix_node.inputs[2])
                    links.new(mix_node.outputs["Color"], principled.inputs["Base Color"])
                    print("Connected ARM.R to AO mix with Base Color")

            # Handle AO (Ambient Occlusion) if separate
            if "ao" in texture_nodes:
                base_color_node = None
                for map_name in ["color", "diffuse", "albedo"]:
                    if map_name in texture_nodes:
                        base_color_node = texture_nodes[map_name]
                        break

                if base_color_node:
                    mix_node = nodes.new(type="ShaderNodeMixRGB")
                    mix_node.location = (100, 200)
                    mix_node.blend_type = "MULTIPLY"
                    mix_node.inputs["Fac"].default_value = 0.8  # 80% influence

                    # Disconnect direct connection to base color
                    for link in base_color_node.outputs["Color"].links:
                        if link.to_socket == principled.inputs["Base Color"]:
                            links.remove(link)

                    # Connect through the mix node
                    links.new(base_color_node.outputs["Color"], mix_node.inputs[1])
                    links.new(texture_nodes["ao"].outputs["Color"], mix_node.inputs[2])
                    links.new(mix_node.outputs["Color"], principled.inputs["Base Color"])
                    print("Connected AO to mix with Base Color")

            # CRITICAL: Make sure to clear all existing materials from the object
            while len(obj.data.materials) > 0:
                obj.data.materials.pop(index=0)

            # Assign the new material to the object
            obj.data.materials.append(new_mat)

            # CRITICAL: Make the object active and select it
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)

            # CRITICAL: Force Blender to update the material
            bpy.context.view_layer.update()

            # Get the list of texture maps
            texture_maps = list(texture_images.keys())

            # Get info about texture nodes for debugging
            material_info = {
                "name": new_mat.name,
                "has_nodes": new_mat.use_nodes,
                "node_count": len(new_mat.node_tree.nodes),
                "texture_nodes": [],
            }

            for node in new_mat.node_tree.nodes:
                if node.type == "TEX_IMAGE" and node.image:
                    connections = []
                    for output in node.outputs:
                        for link in output.links:
                            connections.append(
                                f"{output.name} → {link.to_node.name}.{link.to_socket.name}"
                            )

                    material_info["texture_nodes"].append(
                        {
                            "name": node.name,
                            "image": node.image.name,
                            "colorspace": node.image.colorspace_settings.name,
                            "connections": connections,
                        }
                    )

            return {
                "success": True,
                "message": f"Created new material and applied texture {texture_id} to {object_name}",
                "material": new_mat.name,
                "maps": texture_maps,
                "material_info": material_info,
            }

        except Exception as e:
            print(f"Error in set_texture: {str(e)}")
            traceback.print_exc()
            return {"error": f"Failed to apply texture: {str(e)}"}

    def get_polyhaven_status(self):
        """Get the current status of PolyHaven integration"""
        enabled = bpy.context.scene.blendermcp_use_polyhaven
        if enabled:
            return {
                "enabled": True,
                "message": "PolyHaven integration is enabled and ready to use.",
            }
        else:
            return {
                "enabled": False,
                "message": """PolyHaven integration is currently disabled. To enable it:
                            1. In the 3D Viewport, find the BlenderMCP panel in the sidebar (press N if hidden)
                            2. Check the 'Use assets from Poly Haven' checkbox
                            3. Restart the connection to your LLM client""",
            }

    # region Sketchfab API
    def get_sketchfab_status(self):
        """Get the current status of Sketchfab integration"""
        enabled = bpy.context.scene.blendermcp_use_sketchfab
        api_key = bpy.context.scene.blendermcp_sketchfab_api_key

        # Test the API key if present
        if api_key:
            try:
                headers = {"Authorization": f"Token {api_key}"}

                response = requests.get(
                    "https://api.sketchfab.com/v3/me",
                    headers=headers,
                    timeout=30,  # Add timeout of 30 seconds
                )

                if response.status_code == 200:
                    user_data = response.json()
                    username = user_data.get("username", "Unknown user")
                    return {
                        "enabled": True,
                        "message": f"Sketchfab integration is enabled and ready to use. Logged in as: {username}",
                    }
                else:
                    return {
                        "enabled": False,
                        "message": f"Sketchfab API key seems invalid. Status code: {response.status_code}",
                    }
            except requests.exceptions.Timeout:
                return {
                    "enabled": False,
                    "message": "Timeout connecting to Sketchfab API. Check your internet connection.",
                }
            except Exception as e:
                return {"enabled": False, "message": f"Error testing Sketchfab API key: {str(e)}"}

        if enabled and api_key:
            return {
                "enabled": True,
                "message": "Sketchfab integration is enabled and ready to use.",
            }
        elif enabled and not api_key:
            return {
                "enabled": False,
                "message": """Sketchfab integration is currently enabled, but API key is not given. To enable it:
                            1. In the 3D Viewport, find the BlenderMCP panel in the sidebar (press N if hidden)
                            2. Keep the 'Use Sketchfab' checkbox checked
                            3. Enter your Sketchfab API Key
                            4. Restart the connection to your LLM client""",
            }
        else:
            return {
                "enabled": False,
                "message": """Sketchfab integration is currently disabled. To enable it:
                            1. In the 3D Viewport, find the BlenderMCP panel in the sidebar (press N if hidden)
                            2. Check the 'Use assets from Sketchfab' checkbox
                            3. Enter your Sketchfab API Key
                            4. Restart the connection to your LLM client""",
            }

    def search_sketchfab_models(self, query, categories=None, count=20, downloadable=True):
        """Search for models on Sketchfab based on query and optional filters"""
        try:
            api_key = bpy.context.scene.blendermcp_sketchfab_api_key
            if not api_key:
                return {"error": "Sketchfab API key is not configured"}

            # Build search parameters with exact fields from Sketchfab API docs
            params = {
                "type": "models",
                "q": query,
                "count": count,
                "downloadable": downloadable,
                "archives_flavours": False,
            }

            if categories:
                params["categories"] = categories

            # Make API request to Sketchfab search endpoint
            # The proper format according to Sketchfab API docs for API key auth
            headers = {"Authorization": f"Token {api_key}"}

            # Use the search endpoint as specified in the API documentation
            response = requests.get(
                "https://api.sketchfab.com/v3/search",
                headers=headers,
                params=params,
                timeout=30,  # Add timeout of 30 seconds
            )

            if response.status_code == 401:
                return {"error": "Authentication failed (401). Check your API key."}

            if response.status_code != 200:
                return {"error": f"API request failed with status code {response.status_code}"}

            response_data = response.json()

            # Safety check on the response structure
            if response_data is None:
                return {"error": "Received empty response from Sketchfab API"}

            # Handle 'results' potentially missing from response
            results = response_data.get("results", [])
            if not isinstance(results, list):
                return {"error": f"Unexpected response format from Sketchfab API: {response_data}"}

            return response_data

        except requests.exceptions.Timeout:
            return {"error": "Request timed out. Check your internet connection."}
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON response from Sketchfab API: {str(e)}"}
        except Exception as e:
            import traceback

            traceback.print_exc()
            return {"error": str(e)}

    def download_sketchfab_model(self, uid):
        """Download a model from Sketchfab by its UID"""
        try:
            api_key = bpy.context.scene.blendermcp_sketchfab_api_key
            if not api_key:
                return {"error": "Sketchfab API key is not configured"}

            # Use proper authorization header for API key auth
            headers = {"Authorization": f"Token {api_key}"}

            # Request download URL using the exact endpoint from the documentation
            download_endpoint = f"https://api.sketchfab.com/v3/models/{uid}/download"

            response = requests.get(
                download_endpoint, headers=headers, timeout=30  # Add timeout of 30 seconds
            )

            if response.status_code == 401:
                return {"error": "Authentication failed (401). Check your API key."}

            if response.status_code != 200:
                return {"error": f"Download request failed with status code {response.status_code}"}

            data = response.json()

            # Safety check for None data
            if data is None:
                return {"error": "Received empty response from Sketchfab API for download request"}

            # Extract download URL with safety checks
            gltf_data = data.get("gltf")
            if not gltf_data:
                return {
                    "error": "No gltf download URL available for this model. Response: " + str(data)
                }

            download_url = gltf_data.get("url")
            if not download_url:
                return {
                    "error": "No download URL available for this model. Make sure the model is downloadable and you have access."
                }

            # Download the model with progress tracking (MP-02)
            operation_id = f"sketchfab_{uid}"

            model_response = requests.get(download_url, timeout=60, stream=True)

            if model_response.status_code != 200:
                return {
                    "error": f"Model download failed with status code {model_response.status_code}"
                }

            # Save to temporary file with progress
            temp_dir = tempfile.mkdtemp()
            zip_file_path = os.path.join(temp_dir, f"{uid}.zip")

            total_size = int(model_response.headers.get("content-length", 0))
            downloaded = 0

            if PROGRESS_AVAILABLE:
                tracker = get_progress_tracker()
                if tracker:
                    tracker.start_operation(operation_id, total_size)

            with open(zip_file_path, "wb") as f:
                for chunk in model_response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if PROGRESS_AVAILABLE and tracker:
                            tracker.update_progress(operation_id, downloaded)

            if PROGRESS_AVAILABLE and tracker:
                tracker.complete_operation(operation_id)

            # Extract the zip file with enhanced security
            with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
                # More secure zip slip prevention
                for file_info in zip_ref.infolist():
                    # Get the path of the file
                    file_path = file_info.filename

                    # Convert directory separators to the current OS style
                    # This handles both / and \ in zip entries
                    target_path = os.path.join(temp_dir, os.path.normpath(file_path))

                    # Get absolute paths for comparison
                    abs_temp_dir = os.path.abspath(temp_dir)
                    abs_target_path = os.path.abspath(target_path)

                    # Ensure the normalized path doesn't escape the target directory
                    if not abs_target_path.startswith(abs_temp_dir):
                        with suppress(Exception):
                            shutil.rmtree(temp_dir)
                        return {
                            "error": "Security issue: Zip contains files with path traversal attempt"
                        }

                    # Additional explicit check for directory traversal
                    if ".." in file_path:
                        with suppress(Exception):
                            shutil.rmtree(temp_dir)
                        return {
                            "error": "Security issue: Zip contains files with directory traversal sequence"
                        }

                # If all files passed security checks, extract them
                zip_ref.extractall(temp_dir)

            # Find the main glTF file
            gltf_files = [
                f for f in os.listdir(temp_dir) if f.endswith(".gltf") or f.endswith(".glb")
            ]

            if not gltf_files:
                with suppress(Exception):
                    shutil.rmtree(temp_dir)
                return {"error": "No glTF file found in the downloaded model"}

            main_file = os.path.join(temp_dir, gltf_files[0])

            # Import the model
            bpy.ops.import_scene.gltf(filepath=main_file)

            # Get the names of imported objects
            imported_objects = [obj.name for obj in bpy.context.selected_objects]

            # Clean up temporary files
            with suppress(Exception):
                shutil.rmtree(temp_dir)

            return {
                "success": True,
                "message": "Model imported successfully",
                "imported_objects": imported_objects,
            }

        except requests.exceptions.Timeout:
            return {
                "error": "Request timed out. Check your internet connection and try again with a simpler model."
            }
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON response from Sketchfab API: {str(e)}"}
        except Exception as e:
            import traceback

            traceback.print_exc()
            return {"error": f"Failed to download model: {str(e)}"}

    # endregion


# Blender UI Panel
class BLENDERMCP_PT_Panel(bpy.types.Panel):
    bl_label = "Blender MCP"
    bl_idname = "BLENDERMCP_PT_Panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BlenderMCP"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.prop(scene, "blendermcp_port")
        layout.prop(scene, "blendermcp_use_polyhaven", text="Use assets from Poly Haven")

        layout.prop(scene, "blendermcp_use_sketchfab", text="Use assets from Sketchfab")
        if scene.blendermcp_use_sketchfab:
            self._draw_api_key_warning(layout)
            layout.prop(scene, "blendermcp_sketchfab_api_key", text="API Key")

        if not scene.blendermcp_server_running:
            layout.operator("blendermcp.start_server", text="Connect to MCP server")
        else:
            layout.operator("blendermcp.stop_server", text="Disconnect from MCP server")
            layout.label(text=f"Running on port {scene.blendermcp_port}")

        setup_box = layout.box()
        setup_box.label(text="Local Setup", icon="CONSOLE")
        setup_box.operator(
            "blendermcp.install_dependencies",
            text="Check/Install Dependencies",
            icon="IMPORT",
        )
        setup_box.operator(
            "blendermcp.run_mcp_terminal_server",
            text="Run MCP Server in Terminal",
            icon="PLAY",
        )
        setup_box.prop(scene, "blendermcp_client_target", text="Client")
        setup_box.operator(
            "blendermcp.copy_mcp_client_config",
            text="Copy MCP Client Config",
            icon="COPYDOWN",
        )
        setup_box.operator(
            "blendermcp.health_check",
            text="Health Check",
            icon="CHECKMARK",
        )
        setup_box.operator(
            "blendermcp.open_logs",
            text="Open Logs",
            icon="TEXT",
        )

        status_box = layout.box()
        status_box.label(text="Last Action", icon="INFO")
        if scene.blendermcp_last_action:
            status = "OK" if scene.blendermcp_last_action_ok else "ERROR"
            status_box.label(text=f"{status}: {scene.blendermcp_last_action}")
            status_box.label(text=f"When: {scene.blendermcp_last_action_at}")
            if scene.blendermcp_last_action_details:
                status_box.label(text=scene.blendermcp_last_action_details[:80])
        else:
            status_box.label(text="No action recorded yet.")

        # MP-05: Asset cache management
        layout.separator()
        cache_box = layout.box()
        cache_box.label(text="Asset Cache", icon="FILE_CACHE")
        cache_size, file_count = _asset_cache.get_cache_size()
        size_mb = cache_size / (1024 * 1024)
        cache_box.label(text=f"Files: {file_count}, Size: {size_mb:.1f} MB")
        cache_box.operator("blendermcp.clear_cache", text="Clear Cache", icon="TRASH")

    @staticmethod
    def _draw_api_key_warning(layout):
        """Draw security warning box for API keys."""
        box = layout.box()
        box.alert = True
        box.label(text="⚠️ API keys are saved in .blend file", icon="ERROR")
        box.label(text="Do not share this file publicly", icon="BLANK1")


# Operator to start the server
class BLENDERMCP_OT_StartServer(bpy.types.Operator):
    bl_idname = "blendermcp.start_server"
    bl_label = "Connect to LLM client"
    bl_description = "Start the BlenderMCP server to connect with your LLM client"

    def execute(self, context):
        scene = context.scene

        # Create a new server instance
        if not hasattr(bpy.types, "blendermcp_server") or not bpy.types.blendermcp_server:
            bpy.types.blendermcp_server = BlenderMCPServer(port=scene.blendermcp_port)

        # Start the server
        bpy.types.blendermcp_server.start()
        scene.blendermcp_server_running = True
        _update_action_status(scene, "Connect to MCP server", True, f"Listening on port {scene.blendermcp_port}")

        return {"FINISHED"}


class BLENDERMCP_OT_InstallDependencies(bpy.types.Operator):
    bl_idname = "blendermcp.install_dependencies"
    bl_label = "Check/Install Dependencies"
    bl_description = "Run uv sync --extra gui --extra test in project root"

    def execute(self, context):
        root = _project_root()
        code, output = _run_command(["uv", "--version"], cwd=root)
        if code != 0:
            self.report(
                {"ERROR"},
                "uv not found in PATH. Install uv first, then try again.",
            )
            _update_action_status(context.scene, "Check/Install Dependencies", False, "uv not found")
            return {"CANCELLED"}

        code, output = _run_command(["uv", "sync", "--extra", "gui", "--extra", "test"], cwd=root)
        if code != 0:
            self.report({"ERROR"}, "Dependency sync failed. See Blender console for details.")
            if output:
                print("[blender-mcp] uv sync output:")
                print(output)
            _update_action_status(context.scene, "Check/Install Dependencies", False, "uv sync failed")
            return {"CANCELLED"}

        self.report({"INFO"}, "Dependencies are ready (uv sync completed).")
        _update_action_status(context.scene, "Check/Install Dependencies", True, "uv sync completed")
        return {"FINISHED"}


class BLENDERMCP_OT_RunMCPServerTerminal(bpy.types.Operator):
    bl_idname = "blendermcp.run_mcp_terminal_server"
    bl_label = "Run MCP Server in Terminal"
    bl_description = "Launch uv run blender-mcp --host localhost --port <port> in a new terminal"

    def execute(self, context):
        port = int(context.scene.blendermcp_port)
        root = _project_root()
        host = "localhost"

        try:
            if os.name == "nt":
                cmd = (
                    f'cd /d "{root}" && uv run blender-mcp --host {host} --port {port}'
                )
                subprocess.Popen(["cmd", "/c", "start", "cmd", "/k", cmd])
            else:
                subprocess.Popen(
                    ["uv", "run", "blender-mcp", "--host", host, "--port", str(port)],
                    cwd=root,
                )
        except Exception as exc:
            self.report({"ERROR"}, f"Failed to start MCP server terminal: {exc}")
            _update_action_status(context.scene, "Run MCP Server in Terminal", False, str(exc))
            return {"CANCELLED"}

        self.report({"INFO"}, f"MCP server terminal launched on {host}:{port}.")
        _update_action_status(context.scene, "Run MCP Server in Terminal", True, f"Started on {host}:{port}")
        return {"FINISHED"}


class BLENDERMCP_OT_CopyMCPClientConfig(bpy.types.Operator):
    bl_idname = "blendermcp.copy_mcp_client_config"
    bl_label = "Copy MCP Client Config"
    bl_description = "Copy stdio config snippet for Claude/Cursor/Ollama/LM Studio"

    def execute(self, context):
        scene = context.scene
        client = scene.blendermcp_client_target
        snippet = _mcp_client_config_snippet(client, host="localhost", port=int(scene.blendermcp_port))
        context.window_manager.clipboard = snippet
        self.report({"INFO"}, f"Copied {client} MCP config to clipboard.")
        _update_action_status(scene, "Copy MCP Client Config", True, f"Client: {client}")
        return {"FINISHED"}


class BLENDERMCP_OT_HealthCheck(bpy.types.Operator):
    bl_idname = "blendermcp.health_check"
    bl_label = "Health Check"
    bl_description = "Run local diagnostics (uv + blender-mcp --doctor)"

    def execute(self, context):
        root = _project_root()
        port = int(context.scene.blendermcp_port)
        code, _ = _run_command(["uv", "--version"], cwd=root)
        if code != 0:
            self.report({"ERROR"}, "uv not found in PATH.")
            _update_action_status(context.scene, "Health Check", False, "uv not found")
            return {"CANCELLED"}

        code, output = _run_command(
            ["uv", "run", "blender-mcp", "--doctor", "--host", "localhost", "--port", str(port)],
            cwd=root,
        )
        if output:
            print("[blender-mcp] doctor output:")
            print(output)
        if code != 0:
            self.report({"ERROR"}, "Health check failed. See Blender console.")
            _update_action_status(context.scene, "Health Check", False, "doctor failed")
            return {"CANCELLED"}

        self.report({"INFO"}, "Health check passed. See Blender console for details.")
        _update_action_status(context.scene, "Health Check", True, f"doctor ok for localhost:{port}")
        return {"FINISHED"}


class BLENDERMCP_OT_OpenLogs(bpy.types.Operator):
    bl_idname = "blendermcp.open_logs"
    bl_label = "Open Logs"
    bl_description = "Open Blender MCP log file location"

    def execute(self, context):
        try:
            path = _logs_path()
            if not os.path.exists(path):
                open(path, "a", encoding="utf-8").close()
            _open_in_system(path)
        except Exception as exc:
            self.report({"ERROR"}, f"Could not open logs: {exc}")
            _update_action_status(context.scene, "Open Logs", False, str(exc))
            return {"CANCELLED"}

        self.report({"INFO"}, f"Opened logs: {path}")
        _update_action_status(context.scene, "Open Logs", True, os.path.basename(path))
        return {"FINISHED"}


# Operator to clear asset cache (MP-05)
class BLENDERMCP_OT_ClearCache(bpy.types.Operator):
    bl_idname = "blendermcp.clear_cache"
    bl_label = "Clear Asset Cache"
    bl_description = "Clear all cached downloaded assets from Poly Haven and Sketchfab"

    def execute(self, context):
        deleted = _asset_cache.clear()
        self.report({"INFO"}, f"Cleared {deleted} cached files")
        _update_action_status(context.scene, "Clear Cache", True, f"Deleted files: {deleted}")
        return {"FINISHED"}


# Operator to stop the server
class BLENDERMCP_OT_StopServer(bpy.types.Operator):
    bl_idname = "blendermcp.stop_server"
    bl_label = "Stop the LLM connection"
    bl_description = "Stop the connection to your LLM client"

    def execute(self, context):
        scene = context.scene

        # Stop the server if it exists
        if hasattr(bpy.types, "blendermcp_server") and bpy.types.blendermcp_server:
            bpy.types.blendermcp_server.stop()
            del bpy.types.blendermcp_server

        scene.blendermcp_server_running = False
        _update_action_status(scene, "Disconnect from MCP server", True, "Server stopped")

        return {"FINISHED"}


# MP-02: Modal operator for download progress display
class BLENDERMCP_OT_DownloadProgress(bpy.types.Operator):
    """Display download progress with cancellation support."""

    bl_idname = "blendermcp.download_progress"
    bl_label = "Download Progress"

    operation_id: bpy.props.StringProperty(default="")
    _timer = None
    _last_progress = 0

    def modal(self, context, event):
        if event.type == "TIMER":
            if not PROGRESS_AVAILABLE:
                self.cancel(context)
                return {"CANCELLED"}

            # Get progress update
            tracker = get_progress_tracker()
            if not tracker:
                self.cancel(context)
                return {"CANCELLED"}

            progress_info = tracker.get_progress(self.operation_id)

            if progress_info is None:
                # Operation not found, clean up
                self.cancel(context)
                return {"CANCELLED"}

            # Update progress bar
            progress_pct = int(progress_info.progress_percent)
            if progress_pct != self._last_progress:
                context.window_manager.progress_update(progress_pct)
                self._last_progress = progress_pct

            # Check completion status
            if progress_info.status == "completed":
                context.window_manager.progress_end()
                self.report({"INFO"}, f"Download complete! ({progress_info.format_progress()})")
                self.cancel(context)
                return {"FINISHED"}
            elif progress_info.status == "error":
                context.window_manager.progress_end()
                self.report({"ERROR"}, f"Download failed: {progress_info.error_message}")
                self.cancel(context)
                return {"CANCELLED"}
            elif progress_info.status == "cancelled":
                context.window_manager.progress_end()
                self.report({"WARNING"}, "Download cancelled by user")
                self.cancel(context)
                return {"CANCELLED"}

            # Update area to show progress
            context.area.tag_redraw() if hasattr(context, "area") and context.area else None

        # Allow cancellation with ESC key
        elif event.type == "ESC":
            if PROGRESS_AVAILABLE:
                tracker = get_progress_tracker()
                if tracker:
                    tracker.cancel_operation(self.operation_id)
            context.window_manager.progress_end()
            self.report({"WARNING"}, "Download cancelled (ESC pressed)")
            self.cancel(context)
            return {"CANCELLED"}

        return {"RUNNING_MODAL"}

    def execute(self, context):
        if not PROGRESS_AVAILABLE:
            self.report({"ERROR"}, "Progress tracking not available")
            return {"CANCELLED"}

        if not self.operation_id:
            self.report({"ERROR"}, "No operation ID provided")
            return {"CANCELLED"}

        # Start progress bar
        context.window_manager.progress_begin(0, 100)

        # Register timer (update every 0.1 seconds)
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)

        return {"RUNNING_MODAL"}

    def cancel(self, context):
        if self._timer:
            wm = context.window_manager
            wm.event_timer_remove(self._timer)
            self._timer = None


# Registration functions
def register():
    bpy.types.Scene.blendermcp_port = IntProperty(
        name="Port",
        description="Port number for the BlenderMCP socket server (default: 9876). Must match the port configured in your MCP client.",
        default=9876,
        min=1024,
        max=65535,
    )

    bpy.types.Scene.blendermcp_server_running = bpy.props.BoolProperty(
        name="Server Running",
        description="Indicates whether the MCP server is currently running and accepting connections",
        default=False,
    )

    bpy.types.Scene.blendermcp_use_polyhaven = bpy.props.BoolProperty(
        name="Use Poly Haven",
        description="Enable Poly Haven asset integration. Allows downloading HDRIs, textures, and 3D models from Poly Haven API. Requires internet connection.",
        default=False,
    )

    bpy.types.Scene.blendermcp_use_sketchfab = bpy.props.BoolProperty(
        name="Use Sketchfab",
        description="Enable Sketchfab asset integration. Search and download 3D models from Sketchfab. Requires API key and internet connection.",
        default=False,
    )

    bpy.types.Scene.blendermcp_sketchfab_api_key = bpy.props.StringProperty(
        name="Sketchfab API Key",
        subtype="PASSWORD",
        description="Your Sketchfab API key. Get it from sketchfab.com/settings/password. Only models you have download access to will work. WARNING: Saved in .blend file in plain text.",
        default="",
    )
    bpy.types.Scene.blendermcp_client_target = bpy.props.EnumProperty(
        name="MCP Client",
        description="Client target for config snippet",
        items=[
            ("claude", "Claude Desktop", "Copy config snippet for Claude Desktop"),
            ("cursor", "Cursor", "Copy config snippet for Cursor"),
            ("ollama", "Ollama", "Copy config snippet for an MCP-capable Ollama client"),
            ("lm_studio", "LM Studio", "Copy config snippet for LM Studio"),
        ],
        default="claude",
    )
    bpy.types.Scene.blendermcp_last_action = bpy.props.StringProperty(
        name="Last Action",
        default="",
    )
    bpy.types.Scene.blendermcp_last_action_at = bpy.props.StringProperty(
        name="Last Action At",
        default="",
    )
    bpy.types.Scene.blendermcp_last_action_details = bpy.props.StringProperty(
        name="Last Action Details",
        default="",
    )
    bpy.types.Scene.blendermcp_last_action_ok = bpy.props.BoolProperty(
        name="Last Action OK",
        default=True,
    )

    bpy.utils.register_class(BLENDERMCP_PT_Panel)
    bpy.utils.register_class(BLENDERMCP_OT_StartServer)
    bpy.utils.register_class(BLENDERMCP_OT_StopServer)
    bpy.utils.register_class(BLENDERMCP_OT_InstallDependencies)
    bpy.utils.register_class(BLENDERMCP_OT_RunMCPServerTerminal)
    bpy.utils.register_class(BLENDERMCP_OT_CopyMCPClientConfig)
    bpy.utils.register_class(BLENDERMCP_OT_HealthCheck)
    bpy.utils.register_class(BLENDERMCP_OT_OpenLogs)
    bpy.utils.register_class(BLENDERMCP_OT_ClearCache)
    bpy.utils.register_class(BLENDERMCP_OT_DownloadProgress)

    print("BlenderMCP addon registered")


def unregister():
    # Stop the server if it's running
    if hasattr(bpy.types, "blendermcp_server") and bpy.types.blendermcp_server:
        bpy.types.blendermcp_server.stop()
        del bpy.types.blendermcp_server

    bpy.utils.unregister_class(BLENDERMCP_PT_Panel)
    bpy.utils.unregister_class(BLENDERMCP_OT_StartServer)
    bpy.utils.unregister_class(BLENDERMCP_OT_StopServer)
    bpy.utils.unregister_class(BLENDERMCP_OT_InstallDependencies)
    bpy.utils.unregister_class(BLENDERMCP_OT_RunMCPServerTerminal)
    bpy.utils.unregister_class(BLENDERMCP_OT_CopyMCPClientConfig)
    bpy.utils.unregister_class(BLENDERMCP_OT_HealthCheck)
    bpy.utils.unregister_class(BLENDERMCP_OT_OpenLogs)
    bpy.utils.unregister_class(BLENDERMCP_OT_ClearCache)
    bpy.utils.unregister_class(BLENDERMCP_OT_DownloadProgress)

    del bpy.types.Scene.blendermcp_port
    del bpy.types.Scene.blendermcp_server_running
    del bpy.types.Scene.blendermcp_use_polyhaven
    del bpy.types.Scene.blendermcp_use_sketchfab
    del bpy.types.Scene.blendermcp_sketchfab_api_key
    del bpy.types.Scene.blendermcp_client_target
    del bpy.types.Scene.blendermcp_last_action
    del bpy.types.Scene.blendermcp_last_action_at
    del bpy.types.Scene.blendermcp_last_action_details
    del bpy.types.Scene.blendermcp_last_action_ok

    print("BlenderMCP addon unregistered")


if __name__ == "__main__":
    register()

