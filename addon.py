# Code created by Siddharth Ahuja: www.github.com/ahujasid © 2025

import importlib.util
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


def _load_socket_server_class():
    """Load addon/server.py robustly in both legacy addon and extension modes."""
    addon_pkg_dir = os.path.join(os.path.dirname(__file__), "addon")

    server_path = os.path.join(addon_pkg_dir, "server.py")
    spec = importlib.util.spec_from_file_location("blender_mcp_socket_server", server_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load socket server module from {server_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.BlenderMCPServer


SocketBlenderMCPServer = _load_socket_server_class()

# Import progress tracking for MP-02 (filesystem-based, no sys.path mutation)
try:
    _progress_path = os.path.join(os.path.dirname(__file__), "src", "blender_mcp", "progress.py")
    _progress_spec = importlib.util.spec_from_file_location("_blendermcp_progress", _progress_path)
    _progress_mod = importlib.util.module_from_spec(_progress_spec)
    _progress_spec.loader.exec_module(_progress_mod)
    get_progress_tracker = _progress_mod.get_progress_tracker
    PROGRESS_AVAILABLE = True
except Exception:
    PROGRESS_AVAILABLE = False

    def get_progress_tracker():
        return None


bl_info = {
    "name": "Blender MCP",
    "author": "BlenderMCP",
    "version": (2, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > BlenderMCP",
    "description": "Connect Blender to local LLM clients via MCP",
    "category": "Interface",
}

# Add User-Agent as required by Poly Haven API
REQ_HEADERS = requests.utils.default_headers()
REQ_HEADERS.update({"User-Agent": "blender-mcp"})

# Load network utilities (retry, fallback, logging)
try:
    from addon.utils.network import robust_get, resolve_polyhaven_resolution, friendly_error, log_asset_download, validate_sketchfab_key
except ImportError:
    _net_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "addon", "utils", "network.py")
    _net_spec = importlib.util.spec_from_file_location("_blendermcp_network", _net_path)
    _net_mod = importlib.util.module_from_spec(_net_spec)
    _net_spec.loader.exec_module(_net_mod)
    robust_get = _net_mod.robust_get
    resolve_polyhaven_resolution = _net_mod.resolve_polyhaven_resolution
    friendly_error = _net_mod.friendly_error
    log_asset_download = _net_mod.log_asset_download
    validate_sketchfab_key = _net_mod.validate_sketchfab_key

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


def _uv_command_prefixes() -> list[list[str]]:
    """Return candidate command prefixes to invoke uv across environments."""
    candidates = [["uv"], [sys.executable, "-m", "uv"]]
    if os.name == "nt":
        candidates.append(["py", "-m", "uv"])
    return candidates


def _resolve_uv_command(cwd: str) -> list[str] | None:
    """Find a working uv command prefix or return None."""
    for prefix in _uv_command_prefixes():
        code, _ = _run_command([*prefix, "--version"], cwd=cwd)
        if code == 0:
            return prefix
    return None


def _uv_blender_mcp_command(cwd: str, host: str, port: int, doctor: bool = False) -> list[str] | None:
    """Build a uv command that works both in repo checkout and installed addon mode."""
    uv_prefix = _resolve_uv_command(cwd)
    if uv_prefix is None:
        return None

    pyproject_path = os.path.join(cwd, "pyproject.toml")
    if os.path.exists(pyproject_path):
        cmd = [*uv_prefix, "run", "blender-mcp", "--host", host, "--port", str(port)]
    else:
        cmd = [*uv_prefix, "tool", "run", "blender-mcp", "--host", host, "--port", str(port)]

    if doctor:
        cmd.insert(-4, "--doctor")
    return cmd


def _ensure_pip(cwd: str) -> tuple[bool, str]:
    """Ensure pip is available in current Python runtime."""
    code, out = _run_command([sys.executable, "-m", "pip", "--version"], cwd=cwd)
    if code == 0:
        return True, out
    code, out = _run_command([sys.executable, "-m", "ensurepip", "--upgrade"], cwd=cwd)
    if code != 0:
        return False, out
    code, out = _run_command([sys.executable, "-m", "pip", "--version"], cwd=cwd)
    return code == 0, out


def _install_runtime_dependencies_with_pip(cwd: str) -> tuple[int, str]:
    """Install minimal runtime deps when repo metadata is not available."""
    ok, out = _ensure_pip(cwd)
    if not ok:
        return 1, f"pip unavailable: {out}"
    return _run_command([sys.executable, "-m", "pip", "install", "--upgrade", "requests>=2.25.0"], cwd=cwd)


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
            "configure_render_settings": self.configure_render_settings,
            "setup_camera": self.setup_camera,
            "get_polyhaven_status": self.get_polyhaven_status,
            "get_sketchfab_status": self.get_sketchfab_status,
            "get_ambientcg_status": self.get_ambientcg_status,
            "set_exact_dimensions": self.set_exact_dimensions,
            "apply_print_thickness": self.apply_print_thickness,
            "apply_boolean_operation": self.apply_boolean_operation,
            "export_for_printing": self.export_for_printing,
            "assign_print_color": self.assign_print_color,
            "auto_layout_for_printing": self.auto_layout_for_printing,
            "export_3mf_for_multicolor": self.export_3mf_for_multicolor,
            "separate_loose_parts": self.separate_loose_parts,
            "create_axle_joint": self.create_axle_joint,
            "check_mesh_integrity": self.check_mesh_integrity,
            "auto_repair_mesh": self.auto_repair_mesh,
            "generate_tire_treads": self.generate_tire_treads,
            "setup_simple_vehicle_rig": self.setup_simple_vehicle_rig,
            "setup_product_studio": self.setup_product_studio,
            "render_catalog_angles": self.render_catalog_angles,
            "generate_print_report": self.generate_print_report,
            "batch_export_all_formats": self.batch_export_all_formats,
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

        # Add AmbientCG handlers only if enabled
        if bpy.context.scene.blendermcp_use_ambientcg:
            ambientcg_handlers = {
                "search_ambientcg_materials": self.search_ambientcg_materials,
                "download_ambientcg_material": self.download_ambientcg_material,
            }
            handlers.update(ambientcg_handlers)

        handler = handlers.get(cmd_type)
        if handler:
            try:
                print(f"Executing handler for {cmd_type}")
                result = handler(**params)
                print("Handler execution complete")

                # Push Undo state for commands that likely modify the scene
                read_only_cmds = (
                    "get_scene_info", "get_object_info", "get_polyhaven_categories",
                    "search_polyhaven_assets", "search_sketchfab_models", "search_ambientcg_materials",
                    "get_polyhaven_status", "get_sketchfab_status", "get_ambientcg_status", "get_viewport_screenshot"
                )
                if cmd_type not in read_only_cmds:
                    try:
                        bpy.ops.ed.undo_push(message=f"MCP: {cmd_type}")
                    except Exception as undo_err:
                        print(f"Failed to push undo state: {undo_err}")

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
            # Check scene permission first
            if not bpy.context.scene.blendermcp_allow_code_execution:
                return {"error": "Remote code execution blocked. Enable 'Allow Remote Code Execution' in BlenderMCP UI."}

            import ast
            try:
                tree = ast.parse(code)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name in ("os", "sys", "subprocess", "shutil"):
                                return {"error": f"Security rules block import of '{alias.name}'"}
                    elif isinstance(node, ast.ImportFrom):
                        if node.module in ("os", "sys", "subprocess", "shutil"):
                            return {"error": f"Security rules block import from '{node.module}'"}
            except SyntaxError as e:
                return {"error": f"Syntax error in code: {e}"}

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

            response = robust_get(
                f"https://api.polyhaven.com/categories/{asset_type}", headers=REQ_HEADERS
            )
            if response.status_code == 200:
                return {"categories": response.json()}
            else:
                return {"error": f"Poly Haven API returned status {response.status_code}. Try again later."}
        except Exception as e:
            return friendly_error("Poly Haven categories", e)

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

            response = robust_get(url, params=params, headers=REQ_HEADERS)
            if response.status_code == 200:
                assets = response.json()
                limited_assets = {}
                for i, (key, value) in enumerate(assets.items()):
                    if i >= 20:
                        break
                    limited_assets[key] = value

                return {
                    "assets": limited_assets,
                    "total_count": len(assets),
                    "returned_count": len(limited_assets),
                }
            else:
                return {"error": f"Poly Haven search returned status {response.status_code}. Try again later."}
        except Exception as e:
            return friendly_error("Poly Haven search", e)

    def download_polyhaven_asset(self, asset_id, asset_type, resolution="1k", file_format=None):
        try:
            # First get the files information
            files_response = robust_get(
                f"https://api.polyhaven.com/files/{asset_id}", headers=REQ_HEADERS
            )
            if files_response.status_code != 200:
                return {"error": f"Could not fetch asset '{asset_id}' from Poly Haven (status {files_response.status_code})."}

            files_data = files_response.json()

            # Handle different asset types
            if asset_type == "hdris":
                # For HDRIs, download the .hdr or .exr file
                if not file_format:
                    file_format = "hdr"

                # Use resolution fallback (4k -> 2k -> 1k)
                actual_res, file_info = resolve_polyhaven_resolution(files_data, "hdri", resolution, file_format)
                if file_info is None:
                    return {"error": f"HDRI '{asset_id}' not available in {resolution} ({file_format}). Try a different resolution or format."}

                file_url = file_info["url"]

                tmp_file = tempfile.NamedTemporaryFile(suffix=f".{file_format}", delete=False)
                tmp_path = tmp_file.name
                tmp_file.close()

                try:
                    operation_id = f"polyhaven_hdri_{asset_id}_{actual_res}"

                    response = robust_get(file_url, headers=REQ_HEADERS, stream=True)
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
                        try:
                            env_tex.image.colorspace_settings.name = "Linear"
                        except Exception:
                            env_tex.image.colorspace_settings.name = "Non-Color"
                    else:  # hdr
                        for color_space in ["Linear", "Linear Rec.709", "Non-Color"]:
                            try:
                                env_tex.image.colorspace_settings.name = color_space
                                break
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

                    # Log the download
                    log_asset_download("polyhaven", asset_id, "hdri", actual_res)

                    msg = f"HDRI {asset_id} imported successfully"
                    if actual_res != resolution:
                        msg += f" (used {actual_res} instead of {resolution})"

                    return {
                        "success": True,
                        "message": msg,
                        "image_name": env_tex.image.name,
                    }
                except Exception as e:
                    return {"error": f"Failed to set up HDRI in Blender: {str(e)}"}
                finally:
                    try:
                        if os.path.exists(tmp_path):
                            os.unlink(tmp_path)
                    except Exception as cleanup_error:
                        print(
                            f"Warning: Failed to cleanup temp file {tmp_path}: {cleanup_error}"
                        )

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

                                    response = robust_get(
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

                        response = robust_get(file_url, headers=REQ_HEADERS)
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
                                include_response = robust_get(include_url, headers=REQ_HEADERS)
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

                response = robust_get(
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
            response = robust_get(
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

            response = robust_get(
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

            model_response = robust_get(download_url, timeout=60, stream=True)

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

    # region AmbientCG API
    def search_ambientcg_materials(self, query="", limit=20):
        """Search for materials on AmbientCG"""
        try:
            from addon.handlers.ambientcg import search_ambientcg_materials as _search
            return _search(bpy.context.scene, query=query, limit=limit)
        except Exception as e:
            return {"error": f"Failed to load AmbientCG handler: {str(e)}"}

    def download_ambientcg_material(self, asset_id, resolution="2K", file_format="JPG"):
        """Download and import an AmbientCG material"""
        try:
            from addon.handlers.ambientcg import download_ambientcg_material as _download
            tracker = None
            if PROGRESS_AVAILABLE:
                tracker = get_progress_tracker()
            return _download(bpy.context.scene, asset_id, resolution, file_format, progress_tracker=tracker)
        except Exception as e:
            return {"error": f"Failed to load AmbientCG handler: {str(e)}"}
    
    def get_ambientcg_status(self):
        """Get the status of AmbientCG integration"""
        try:
            from addon.handlers.ambientcg import get_ambientcg_status as _status
            return _status(bpy.context.scene)
        except Exception as e:
            return {"error": f"Failed to load AmbientCG handler: {str(e)}"}
    # endregion

    # region Scene Tools
    def configure_render_settings(self, engine="BLENDER_EEVEE", resolution_x=1920, resolution_y=1080, samples=64, use_gpu=True, transparent_background=False):
        """Configure render engine and settings"""
        try:
            from addon.handlers.scene_tools import configure_render_settings as _config
            return _config(bpy.context.scene, engine, resolution_x, resolution_y, samples, use_gpu, transparent_background)
        except Exception as e:
            return {"error": f"Failed to access scene tools: {str(e)}"}

    def setup_camera(self, focus_object_name=None, location=(0, -10, 5), create_new=False):
        """Setup main camera to point at an object"""
        try:
            from addon.handlers.scene_tools import setup_camera as _setup
            # Ensure location is passed as a tuple/list to match API
            loc_tuple = tuple(location) if isinstance(location, (list, tuple)) else (0, -10, 5)
            return _setup(bpy.context.scene, focus_object_name, loc_tuple, create_new)
        except Exception as e:
            return {"error": f"Failed to setup camera: {str(e)}"}
    # endregion

    # region 3D Printing Tools
    def set_exact_dimensions(self, object_name, size_x=None, size_y=None, size_z=None):
        """Set exact dimensions for precise 3D printing"""
        try:
            from addon.handlers.printing3d import set_exact_dimensions as _set_dims
            return _set_dims(bpy.context.scene, object_name, size_x, size_y, size_z)
        except Exception as e:
            return {"error": f"Failed to execute set_exact_dimensions: {str(e)}"}
            
    def apply_print_thickness(self, object_name, thickness_mm, offset=0.0):
        """Apply Solidify modifier to create printer-friendly shells"""
        try:
            from addon.handlers.printing3d import apply_print_thickness as _apply_thick
            return _apply_thick(bpy.context.scene, object_name, thickness_mm, offset)
        except Exception as e:
            return {"error": f"Failed to execute apply_print_thickness: {str(e)}"}

    def apply_boolean_operation(self, target_name, tool_name, operation="DIFFERENCE"):
        """Use boolean operations to cut or union parts"""
        try:
            from addon.handlers.printing3d import apply_boolean_operation as _bool_op
            return _bool_op(bpy.context.scene, target_name, tool_name, operation)
        except Exception as e:
            return {"error": f"Failed to execute apply_boolean_operation: {str(e)}"}

    def export_for_printing(self, object_names=None, filepath=None):
        """Export objects to STL format"""
        try:
            from addon.handlers.printing3d import export_for_printing as _export
            return _export(bpy.context.scene, object_names, filepath)
        except Exception as e:
            return {"error": f"Failed to execute export_for_printing: {str(e)}"}
            
    def assign_print_color(self, object_name, hex_color):
        """Assign base color to object for 3D printing (stored in material)"""
        try:
            from addon.handlers.printing3d import assign_print_color as _color
            return _color(bpy.context.scene, object_name, hex_color)
        except Exception as e:
            return {"error": f"Failed to assign print color: {str(e)}"}
            
    def auto_layout_for_printing(self, bed_size_x=256, bed_size_y=256, padding_mm=5):
        """Auto layout all meshes flat on the Z=0 bed with spacing"""
        try:
            from addon.handlers.printing3d import auto_layout_for_printing as _layout
            return _layout(bpy.context.scene, bed_size_x, bed_size_y, padding_mm)
        except Exception as e:
            return {"error": f"Failed to auto layout for printing: {str(e)}"}
            
    def export_3mf_for_multicolor(self, filepath=None):
        """Export the scene to .3mf, preserving colors/materials for BambuStudio"""
        try:
            from addon.handlers.printing3d import export_3mf_for_multicolor as _export3mf
            return _export3mf(bpy.context.scene, filepath)
        except Exception as e:
            return {"error": f"Failed to export 3MF: {str(e)}"}
    # endregion

    # region Mesh Tools
    def separate_loose_parts(self, object_name, smart_rename=True):
        """Separate a mesh into loose parts with smart renaming"""
        try:
            from addon.handlers.mesh_tools import separate_loose_parts as _separate
            return _separate(bpy.context.scene, object_name, smart_rename)
        except Exception as e:
            return {"error": f"Failed to separate mesh: {str(e)}"}
            
    def check_mesh_integrity(self, object_name):
        """Check mesh for non-manifold issues and holes"""
        try:
            from addon.handlers.mesh_tools import check_mesh_integrity as _check
            return _check(bpy.context.scene, object_name)
        except Exception as e:
            return {"error": f"Failed to check mesh integrity: {str(e)}"}
            
    def auto_repair_mesh(self, object_name):
        """Try to auto-repair common mesh issues"""
        try:
            from addon.handlers.mesh_tools import auto_repair_mesh as _repair
            return _repair(bpy.context.scene, object_name)
        except Exception as e:
            return {"error": f"Failed to auto-repair mesh: {str(e)}"}
    # endregion

    # region Procedural Tools
    def generate_tire_treads(self, wheel_name, pattern='OFFROAD'):
        """Generate procedural treads on a wheel"""
        try:
            from addon.handlers.procedural_tools import generate_tire_treads as _treads
            return _treads(bpy.context.scene, wheel_name, pattern)
        except Exception as e:
            return {"error": f"Failed to generate treads: {str(e)}"}
    # endregion

    # region Vehicle Tools
    def setup_simple_vehicle_rig(self, chassis_name, wheel_names):
        """Setup a basic rig for a vehicle"""
        try:
            from addon.handlers.vehicle_rigging import setup_simple_vehicle_rig as _rig
            return _rig(bpy.context.scene, chassis_name, wheel_names)
        except Exception as e:
            return {"error": f"Failed to setup vehicle rig: {str(e)}"}
    # endregion

    # region Mechanical Tools
    def create_axle_joint(self, chassis_name, wheel_name, axle_diameter=None, clearance=0.2, hole_depth=None):
        """Create a mechanical axle joint between chassis and wheel"""
        try:
            from addon.handlers.mechanical_tools import create_axle_joint as _axle
            return _axle(bpy.context.scene, chassis_name, wheel_name, axle_diameter, clearance, hole_depth)
        except Exception as e:
            return {"error": f"Failed to create axle joint: {str(e)}"}
    # endregion

    # region Studio Tools
    def setup_product_studio(self, theme='CLEAN'):
        """Setup a professional studio environment"""
        try:
            from addon.handlers.studio_tools import setup_product_studio as _studio
            return _studio(bpy.context.scene, theme)
        except Exception as e:
            return {"error": f"Failed to setup studio: {str(e)}"}
            
    def render_catalog_angles(self, output_dir=None):
        """Render catalog angles"""
        try:
            from addon.handlers.studio_tools import render_catalog_angles as _render
            return _render(bpy.context.scene, output_dir)
        except Exception as e:
            return {"error": f"Failed to render catalog: {str(e)}"}
    # endregion

    # region Reporting Tools
    def generate_print_report(self, filepath=None):
        """Generate a technical print report"""
        try:
            from addon.handlers.reporting_tools import generate_print_report as _report
            return _report(bpy.context.scene, filepath)
        except Exception as e:
            return {"error": f"Failed to generate report: {str(e)}"}
    # endregion

    # region Export Tools
    def batch_export_all_formats(self, base_path=None):
        """One-click batch export for all formats"""
        try:
            from addon.handlers.printing3d import batch_export_all_formats as _batch
            return _batch(bpy.context.scene, base_path)
        except Exception as e:
            return {"error": f"Failed batch export: {str(e)}"}
    # endregion


# Blender UI Panel and Operators are now in addon/ui/ package.
# Load via filesystem to work in all Blender loading modes (repo, extension, legacy).
import importlib.util as _iu

_ui_init = os.path.join(os.path.dirname(os.path.abspath(__file__)), "addon", "ui", "__init__.py")
_spec = _iu.spec_from_file_location("_blendermcp_ui", _ui_init)
_mod = _iu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_UI_CLASSES = _mod.UI_CLASSES


# Registration functions
def register():
    bpy.types.Scene.blendermcp_port = IntProperty(
        name="Port",
        description="Port number for the BlenderMCP socket server (default: 9876). Must match the port configured in your MCP client.",
        default=9876,
        min=1024,
        max=65535,
    )
    bpy.types.Scene.blendermcp_allow_code_execution = bpy.props.BoolProperty(
        name="Allow Remote Code Execution",
        description="WARNING: Allows the LLM to execute arbitrary Python code. Enable only if you trust the requests",
        default=False,
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

    bpy.types.Scene.blendermcp_use_ambientcg = bpy.props.BoolProperty(
        name="Use AmbientCG",
        description="Enable AmbientCG asset integration. Search and download PBR textures from AmbientCG API.",
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

    for cls in _UI_CLASSES:
        bpy.utils.register_class(cls)

    print("BlenderMCP addon registered")


def unregister():
    # Stop the server if it's running
    if hasattr(bpy.types, "blendermcp_server") and bpy.types.blendermcp_server:
        bpy.types.blendermcp_server.stop()
        del bpy.types.blendermcp_server

    for cls in reversed(_UI_CLASSES):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.blendermcp_port
    del bpy.types.Scene.blendermcp_server_running
    del bpy.types.Scene.blendermcp_use_polyhaven
    del bpy.types.Scene.blendermcp_use_ambientcg
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

