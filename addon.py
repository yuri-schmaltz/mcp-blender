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
    
    # Try relative import first if in a package
    if __package__:
        try:
            from .addon.server import BlenderMCPServer
            return BlenderMCPServer
        except (ImportError, ValueError):
            pass

    spec = importlib.util.spec_from_file_location("blender_mcp_socket_server", server_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load socket server module from {server_path}")
    module = importlib.util.module_from_spec(spec)
    # Carry over package if possible
    if __package__:
        module.__package__ = __package__
    spec.loader.exec_module(module)
    return module.BlenderMCPServer


SocketBlenderMCPServer = _load_socket_server_class()

# Import progress tracking for MP-02 (filesystem-based, no sys.path mutation)
try:
    if __package__:
        from .src.blender_mcp.progress import get_progress_tracker
    else:
        _progress_path = os.path.join(os.path.dirname(__file__), "src", "blender_mcp", "progress.py")
        _progress_spec = importlib.util.spec_from_file_location("_blendermcp_progress", _progress_path)
        _progress_mod = importlib.util.module_from_spec(_progress_spec)
        if __package__:
            _progress_mod.__package__ = __package__
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
    "version": (2, 4, 1),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > BlenderMCP",
    "description": "Connect Blender to local LLM clients via MCP",
    "category": "Interface",
}

# MP-05: Persistence and asset caching
try:
    if __package__:
        from .addon.utils.cache import get_asset_cache
        from .addon.utils.network import robust_get
        from .addon.utils.constants import REQ_HEADERS
    else:
        from addon.utils.cache import get_asset_cache
        from addon.utils.network import robust_get
        from addon.utils.constants import REQ_HEADERS
except ImportError:
    # Minimal fallback if utils not found (shouldn't happen in production)
    from contextlib import suppress
    def get_asset_cache():
        class MockCache:
            def get(self, *args): return None
            def put(self, *args, **kwargs): return args[2]
        return MockCache()
    def robust_get(url, **kwargs): return requests.get(url, **kwargs)
    REQ_HEADERS = {"User-Agent": "blender-mcp"}

# Helper for dynamic handler loading
def _call_handler(module_name, func_name, *args, **kwargs):
    """Dynamically load and call a handler function."""
    try:
        if __package__:
            module = __import__(f"{__package__}.addon.handlers.{module_name}", fromlist=[func_name])
        else:
            module = __import__(f"addon.handlers.{module_name}", fromlist=[func_name])
        func = getattr(module, func_name)
        return func(*args, **kwargs)
    except Exception as e:
        print(f"Error calling handler {module_name}.{func_name}: {e}")
        traceback.print_exc()
        return {"error": f"Handler {module_name} error: {str(e)}"}

# Load network utilities (retry, fallback, logging)
try:
    if __package__:
        from .addon.utils.network import robust_get, resolve_polyhaven_resolution, friendly_error, log_asset_download, validate_sketchfab_key
    else:
        from addon.utils.network import robust_get, resolve_polyhaven_resolution, friendly_error, log_asset_download, validate_sketchfab_key
except (ImportError, ValueError):
    _net_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "addon", "utils", "network.py")
    _net_spec = importlib.util.spec_from_file_location("_blendermcp_network", _net_path)
    _net_mod = importlib.util.module_from_spec(_net_spec)
    if __package__:
        _net_mod.__package__ = __package__
    _net_spec.loader.exec_module(_net_mod)
    robust_get = _net_mod.robust_get
    resolve_polyhaven_resolution = _net_mod.resolve_polyhaven_resolution
    friendly_error = _net_mod.friendly_error
    log_asset_download = _net_mod.log_asset_download
    validate_sketchfab_key = _net_mod.validate_sketchfab_key

# Global cache instance
_asset_cache = get_asset_cache()


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
        
        # Base handlers
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
            "create_hinge_joint": self.create_hinge_joint,
            "create_snap_fit": self.create_snap_fit,
            "create_ball_joint": self.create_ball_joint,
            "create_screw_hole": self.create_screw_hole,
            "snap_objects_by_proximity": self.snap_objects_by_proximity,
            "set_clearance_tolerance": self.set_clearance_tolerance,
            "mark_as_functional_part": self.mark_as_functional_part,
            "list_functional_parts": self.list_functional_parts,
            "check_mesh_integrity": self.check_mesh_integrity,
            "auto_repair_mesh": self.auto_repair_mesh,
            "resolve_self_intersections": self.resolve_self_intersections,
            "generate_tire_treads": self.generate_tire_treads,
            "setup_simple_vehicle_rig": self.setup_simple_vehicle_rig,
            "setup_product_studio": self.setup_product_studio,
            "render_catalog_angles": self.render_catalog_angles,
            "generate_print_report": self.generate_print_report,
            "batch_export_all_formats": self.batch_export_all_formats,
            # Polyhaven tools
            "get_polyhaven_categories": self.get_polyhaven_categories,
            "search_polyhaven_assets": self.search_polyhaven_assets,
            "download_polyhaven_asset": self.download_polyhaven_asset,
            "set_texture": self.set_texture,
            # Sketchfab tools
            "search_sketchfab_models": self.search_sketchfab_models,
            "download_sketchfab_model": self.download_sketchfab_model,
            # AmbientCG tools
            "search_ambientcg_materials": self.search_ambientcg_materials,
            "download_ambientcg_material": self.download_ambientcg_material,
            # Scene manipulation
            "get_active_object": self.get_active_object,
            "set_active_object": self.set_active_object,
            "transform_object": self.transform_object,
            "add_primitive": self.add_primitive,
            "delete_object": self.delete_object,
            # Operator discovery
            "list_blender_operators": self.list_blender_operators,
            "get_operator_help": self.get_operator_help,
        }

        handler = handlers.get(cmd_type)
        if handler:
            try:
                result = handler(**params)
                
                # Push Undo state
                read_only_cmds = (
                    "get_scene_info", "get_object_info", "get_polyhaven_categories",
                    "search_polyhaven_assets", "search_sketchfab_models", "search_ambientcg_materials",
                    "get_polyhaven_status", "get_sketchfab_status", "get_ambientcg_status", "get_viewport_screenshot"
                )
                if cmd_type not in read_only_cmds:
                    try:
                        bpy.ops.ed.undo_push(message=f"MCP: {cmd_type}")
                    except: pass

                return {"status": "success", "result": result}
            except Exception as e:
                traceback.print_exc()
                return {"status": "error", "message": str(e)}
        return {"status": "error", "message": f"Unknown command type: {cmd_type}"}

    # Delegation methods
    def get_scene_info(self, **kwargs):
        return _call_handler("scene_tools", "get_scene_info", bpy.context.scene, **kwargs)
    
    def get_object_info(self, name):
        return _call_handler("scene_tools", "get_object_info", bpy.context.scene, name)
    
    def get_viewport_screenshot(self, max_size=800, filepath=None, format="png"):
        return _call_handler("scene_tools", "get_viewport_screenshot", bpy.context.scene, max_size, filepath, format)

    def execute_code(self, code):
        if not bpy.context.scene.blendermcp_allow_code_execution:
            return {"error": "Code execution blocked."}
        try:
            namespace = {"bpy": bpy}
            capture_buffer = io.StringIO()
            with redirect_stdout(capture_buffer):
                exec(code, namespace)
            return {"executed": True, "result": capture_buffer.getvalue()}
        except Exception as e:
            return {"error": str(e)}

    def configure_render_settings(self, **kwargs):
        return _call_handler("scene_tools", "configure_render_settings", bpy.context.scene, **kwargs)

    def setup_camera(self, **kwargs):
        return _call_handler("scene_tools", "setup_camera", bpy.context.scene, **kwargs)

    def get_polyhaven_status(self):
        return _call_handler("polyhaven", "get_polyhaven_status", bpy.context.scene)

    def get_polyhaven_categories(self, asset_type="hdris"):
        return _call_handler("polyhaven", "get_polyhaven_categories", asset_type)

    def search_polyhaven_assets(self, query, asset_type="hdris"):
        return _call_handler("polyhaven", "search_polyhaven_assets", query, asset_type)

    def download_polyhaven_asset(self, asset_id, asset_type, resolution="1k"):
        return _call_handler("polyhaven", "download_polyhaven_asset", bpy.context.scene, asset_id, asset_type, resolution)

    def set_texture(self, object_name, texture_id):
        return _call_handler("material_tools", "set_texture", object_name, texture_id)

    def get_sketchfab_status(self):
        return _call_handler("sketchfab", "get_sketchfab_status", bpy.context.scene)

    def search_sketchfab_models(self, query, **kwargs):
        return _call_handler("sketchfab", "search_sketchfab_models", bpy.context.scene, query, **kwargs)

    def download_sketchfab_model(self, uid):
        return _call_handler("sketchfab", "download_sketchfab_model", bpy.context.scene, uid)

    def get_ambientcg_status(self):
        return _call_handler("ambientcg", "get_ambientcg_status", bpy.context.scene)

    def search_ambientcg_materials(self, query="", limit=20):
        return _call_handler("ambientcg", "search_ambientcg_materials", bpy.context.scene, query, limit)

    def download_ambientcg_material(self, asset_id, resolution="2K", file_format="JPG"):
        return _call_handler("ambientcg", "download_ambientcg_material", bpy.context.scene, asset_id, resolution, file_format)

    def set_exact_dimensions(self, **kwargs):
        return _call_handler("printing3d", "set_exact_dimensions", bpy.context.scene, **kwargs)

    def apply_print_thickness(self, **kwargs):
        return _call_handler("printing3d", "apply_print_thickness", bpy.context.scene, **kwargs)

    def apply_boolean_operation(self, **kwargs):
        return _call_handler("printing3d", "apply_boolean_operation", bpy.context.scene, **kwargs)

    def export_for_printing(self, **kwargs):
        return _call_handler("printing3d", "export_for_printing", bpy.context.scene, **kwargs)

    def assign_print_color(self, **kwargs):
        return _call_handler("printing3d", "assign_print_color", bpy.context.scene, **kwargs)

    def auto_layout_for_printing(self, **kwargs):
        return _call_handler("printing3d", "auto_layout_for_printing", bpy.context.scene, **kwargs)

    def export_3mf_for_multicolor(self, **kwargs):
        return _call_handler("printing3d", "export_3mf_for_multicolor", bpy.context.scene, **kwargs)

    def separate_loose_parts(self, **kwargs):
        return _call_handler("mesh_tools", "separate_loose_parts", bpy.context.scene, **kwargs)

    def create_axle_joint(self, **kwargs):
        return _call_handler("mechanical_tools", "create_axle_joint", bpy.context.scene, **kwargs)

    def check_mesh_integrity(self, **kwargs):
        return _call_handler("mesh_tools", "check_mesh_integrity", bpy.context.scene, **kwargs)

    def auto_repair_mesh(self, **kwargs):
        return _call_handler("mesh_tools", "auto_repair_mesh", bpy.context.scene, **kwargs)

    def resolve_self_intersections(self, **kwargs):
        return _call_handler("mesh_tools", "resolve_self_intersections", bpy.context.scene, **kwargs)

    def generate_tire_treads(self, **kwargs):
        return _call_handler("procedural_tools", "generate_tire_treads", bpy.context.scene, **kwargs)

    def setup_simple_vehicle_rig(self, **kwargs):
        return _call_handler("vehicle_rigging", "setup_simple_vehicle_rig", bpy.context.scene, **kwargs)

    def setup_product_studio(self, **kwargs):
        return _call_handler("studio_tools", "setup_product_studio", bpy.context.scene, **kwargs)

    def get_active_object(self):
        return _call_handler("scene_tools", "get_active_object", bpy.context.scene)
    
    def set_active_object(self, **kwargs):
        return _call_handler("scene_tools", "set_active_object", bpy.context.scene, **kwargs)

    def transform_object(self, **kwargs):
        return _call_handler("transform_tools", "transform_object", bpy.context.scene, **kwargs)

    def add_primitive(self, **kwargs):
        return _call_handler("transform_tools", "add_primitive", bpy.context.scene, **kwargs)

    def delete_object(self, **kwargs):
        return _call_handler("transform_tools", "delete_object", bpy.context.scene, **kwargs)

    def list_blender_operators(self, **kwargs):
        return _call_handler("operator_tools", "list_blender_operators", bpy.context.scene, **kwargs)

    def get_operator_help(self, **kwargs):
        return _call_handler("operator_tools", "get_operator_help", bpy.context.scene, **kwargs)

    def render_catalog_angles(self, **kwargs):
        return _call_handler("reporting_tools", "render_catalog_angles", bpy.context.scene, **kwargs)

    def generate_print_report(self, **kwargs):
        return _call_handler("reporting_tools", "generate_print_report", bpy.context.scene, **kwargs)

    def batch_export_all_formats(self, **kwargs):
        return _call_handler("printing3d", "batch_export_all_formats", bpy.context.scene, **kwargs)

    def create_hinge_joint(self, **kwargs):
        return _call_handler("mechanical_tools", "create_hinge_joint", bpy.context.scene, **kwargs)

    def create_snap_fit(self, **kwargs):
        return _call_handler("mechanical_tools", "create_snap_fit", bpy.context.scene, **kwargs)

    def create_ball_joint(self, **kwargs):
        return _call_handler("mechanical_tools", "create_ball_joint", bpy.context.scene, **kwargs)

    def create_screw_hole(self, **kwargs):
        return _call_handler("mechanical_tools", "create_screw_hole", bpy.context.scene, **kwargs)

    def snap_objects_by_proximity(self, **kwargs):
        return _call_handler("printing3d", "snap_objects_by_proximity", bpy.context.scene, **kwargs)

    def set_clearance_tolerance(self, **kwargs):
        return _call_handler("printing3d", "set_clearance_tolerance", bpy.context.scene, **kwargs)

    def mark_as_functional_part(self, **kwargs):
        return _call_handler("functional_parts", "mark_as_functional_part", bpy.context.scene, **kwargs)

    def list_functional_parts(self, **kwargs):
        return _call_handler("functional_parts", "list_functional_parts", bpy.context.scene, **kwargs)

    # endregion


# Blender UI Panel and Operators are now in addon/ui/ package.
# Load via filesystem to work in all Blender loading modes (repo, extension, legacy).
import importlib.util as _iu

_ui_init = os.path.join(os.path.dirname(os.path.abspath(__file__)), "addon", "ui", "__init__.py")
_spec = _iu.spec_from_file_location("_blendermcp_ui", _ui_init)
_mod = _iu.module_from_spec(_spec)
if __package__:
    _mod.__package__ = __package__
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

    bpy.types.Scene.blendermcp_use_blenderkit = bpy.props.BoolProperty(
        name="Use BlenderKit",
        description="Enable BlenderKit asset integration. Search and download models, materials, and textures from BlenderKit API.",
        default=False,
    )

    bpy.types.Scene.blendermcp_sketchfab_api_key = bpy.props.StringProperty(
        name="Sketchfab API Key",
        subtype="PASSWORD",
        description="Your Sketchfab API key. Get it from sketchfab.com/settings/password. Only models you have download access to will work. WARNING: Saved in .blend file in plain text.",
        default="",
    )

    bpy.types.Scene.blendermcp_blenderkit_api_key = bpy.props.StringProperty(
        name="BlenderKit API Token",
        subtype="PASSWORD",
        description="Your BlenderKit API token. Get it from blenderkit.com/settings/profile. WARNING: Saved in .blend file in plain text.",
        default="",
    )

    # Online LLM Integration
    bpy.types.Scene.blendermcp_llm_provider = bpy.props.EnumProperty(
        name="Provider",
        description="Select the online LLM provider to use",
        items=[
            ("OPENAI", "OpenAI", "Use OpenAI models (GPT-4o, etc.)"),
            ("ANTHROPIC", "Anthropic", "Use Anthropic models (Claude 3.5, etc.)"),
            ("GOOGLE", "Google", "Use Google Gemini models"),
        ],
        default="OPENAI",
    )

    bpy.types.Scene.blendermcp_openai_key = bpy.props.StringProperty(
        name="OpenAI API Key",
        subtype="PASSWORD",
        description="Your OpenAI API key. WARNING: Saved in .blend file in plain text.",
        default="",
    )

    bpy.types.Scene.blendermcp_anthropic_key = bpy.props.StringProperty(
        name="Anthropic API Key",
        subtype="PASSWORD",
        description="Your Anthropic API key. WARNING: Saved in .blend file in plain text.",
        default="",
    )

    bpy.types.Scene.blendermcp_google_key = bpy.props.StringProperty(
        name="Google API Key",
        subtype="PASSWORD",
        description="Your Google Gemini API key. WARNING: Saved in .blend file in plain text.",
        default="",
    )

    bpy.types.Scene.blendermcp_openai_model = bpy.props.EnumProperty(
        name="Model",
        items=[
            ("gpt-4o", "GPT-4o", "OpenAI's most capable model"),
            ("gpt-4o-mini", "GPT-4o Mini", "Fast and efficient model"),
            ("gpt-3.5-turbo", "GPT-3.5 Turbo", "Legacy balanced model"),
        ],
        default="gpt-4o",
    )

    bpy.types.Scene.blendermcp_anthropic_model = bpy.props.EnumProperty(
        name="Model",
        items=[
            ("claude-3-5-sonnet-20240620", "Claude 3.5 Sonnet", "Most advanced Claude model"),
            ("claude-3-opus-20240229", "Claude 3 Opus", "Most capable model for complex tasks"),
            ("claude-3-haiku-20240307", "Claude 3 Haiku", "Fastest and most compact model"),
        ],
        default="claude-3-5-sonnet-20240620",
    )

    bpy.types.Scene.blendermcp_google_model = bpy.props.EnumProperty(
        name="Model",
        items=[
            ("gemini-1.5-pro", "Gemini 1.5 Pro", "Most capable Gemini model"),
            ("gemini-1.5-flash", "Gemini 1.5 Flash", "Fast and optimized Gemini model"),
        ],
        default="gemini-1.5-pro",
    )

    bpy.types.Scene.blendermcp_chat_prompt = bpy.props.StringProperty(
        name="Ask AI",
        description="Type your command for the AI assistant",
        default="",
    )

    bpy.types.Scene.blendermcp_chat_status = bpy.props.StringProperty(
        name="AI Status",
        default="",
    )

    # Dynamic client detection – import via filesystem for Blender compat
    if __package__:
        from .addon.utils.helpers import detect_installed_clients as _detect_clients
    else:
        from addon.utils.helpers import detect_installed_clients as _detect_clients

    def _client_items_callback(self, context):  # noqa: ARG001
        return _detect_clients()

    bpy.types.Scene.blendermcp_client_target = bpy.props.EnumProperty(
        name="MCP Client",
        description="Client target for config snippet (auto-detected)",
        items=_client_items_callback,
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
    bpy.types.Scene.blendermcp_show_advanced = bpy.props.BoolProperty(
        name="Show Advanced Settings",
        description="Show technical configuration and manual server commands",
        default=False,
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
        try:
            if hasattr(cls, "bl_rna"):
                bpy.utils.unregister_class(cls)
        except Exception:
            pass

    del bpy.types.Scene.blendermcp_port
    del bpy.types.Scene.blendermcp_allow_code_execution
    del bpy.types.Scene.blendermcp_server_running
    del bpy.types.Scene.blendermcp_use_polyhaven
    del bpy.types.Scene.blendermcp_use_ambientcg
    del bpy.types.Scene.blendermcp_use_sketchfab
    del bpy.types.Scene.blendermcp_use_blenderkit
    del bpy.types.Scene.blendermcp_sketchfab_api_key
    del bpy.types.Scene.blendermcp_blenderkit_api_key
    del bpy.types.Scene.blendermcp_client_target
    del bpy.types.Scene.blendermcp_last_action
    del bpy.types.Scene.blendermcp_last_action_at
    del bpy.types.Scene.blendermcp_last_action_details
    del bpy.types.Scene.blendermcp_last_action_ok
    del bpy.types.Scene.blendermcp_show_advanced

    # Online LLM
    del bpy.types.Scene.blendermcp_llm_provider
    del bpy.types.Scene.blendermcp_openai_key
    del bpy.types.Scene.blendermcp_anthropic_key
    del bpy.types.Scene.blendermcp_google_key
    del bpy.types.Scene.blendermcp_openai_model
    del bpy.types.Scene.blendermcp_anthropic_model
    del bpy.types.Scene.blendermcp_google_model
    del bpy.types.Scene.blendermcp_chat_prompt
    del bpy.types.Scene.blendermcp_chat_status


    print("BlenderMCP addon unregistered")


if __name__ == "__main__":
    register()

