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
import logging
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


def get_prefs():
    """Access global addon preferences via unified helper."""
    try:
        if __package__:
            from .addon.utils.helpers import get_addon_prefs
        else:
            from addon.utils.helpers import get_addon_prefs
        return get_addon_prefs(__package__)
    except ImportError:
        return bpy.context.preferences.addons[_ADDON_PACKAGE].preferences


SocketBlenderMCPServer = _load_socket_server_class()

# Load tool schemas for MCP compliance
try:
    if __package__:
        from .addon import tool_schemas
    else:
        import addon.tool_schemas as tool_schemas
except ImportError:
    tool_schemas = None

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
    "version": (2, 8, 0),
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

# _call_handler removed in favor of direct imports or router.execute_command

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

# Unified helper imports (re-export for backward compatibility with operators.py if needed)
try:
    if __package__:
        from .addon.utils.helpers import (
            _project_root, _run_command, _uv_blender_mcp_command, 
            _update_action_status, _logs_path, _open_in_system
        )
    else:
        from addon.utils.helpers import (
            _project_root, _run_command, _uv_blender_mcp_command, 
            _update_action_status, _logs_path, _open_in_system
        )
except ImportError:
    # Minimal fallbacks if helpers are missing
    def _project_root(): return os.path.dirname(os.path.abspath(__file__))
    def _logs_path(): return os.path.join(_project_root(), "blender_mcp.log")
    def _update_action_status(*args): pass
    def _open_in_system(*args): pass


try:
    if __package__:
        from .addon.core.router import execute_command
        # Initialize handlers
        from .addon.handlers import load_all_handlers
    else:
        from addon.core.router import execute_command
        from addon.handlers import load_all_handlers
except Exception as e:
    import traceback
    traceback.print_exc()
    def execute_command(*args, **kwargs):
        return {"error": f"Router failed to load: {e}"}

class BlenderMCPServer(SocketBlenderMCPServer):
    def __init__(self, host="localhost", port=9876):
        super().__init__(host=host, port=port)
        self.command_executor = execute_command


def _get_addon_package():
    """Resolve the root extension/addon package name for bl_idname.
    
    In Blender 4.2+ Extension mode, __package__ is e.g. 'bl_ext.user_default.mcp_blender'.
    In legacy addon mode, it's the addon folder name or empty.
    This must exactly match the key Blender uses in bpy.context.preferences.addons.
    """
    pkg = __package__
    if not pkg:
        return "mcp_blender"
    # For extensions loaded via bl_ext, the root is always the first 3 parts
    # e.g. 'bl_ext.user_default.mcp_blender' (even if __package__ has extra sub-levels)
    if pkg.startswith("bl_ext."):
        parts = pkg.split(".")
        return ".".join(parts[:3]) if len(parts) >= 3 else pkg
    # For legacy addons, it's just the top-level package
    return pkg.split(".")[0]


_ADDON_PACKAGE = _get_addon_package()


# Removed duplicate BlenderMCPPreferences class. 
# The authoritative AddonPreferences class is defined and registered in __init__.py.


# Blender UI Panel and Operators are now in addon/ui/ package.
from .addon import ui
_UI_CLASSES = ui.UI_CLASSES


# Registration functions
def register():
    # Configure logging to file
    log_path = _logs_path()
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        force=True
    )
    logging.info("BlenderMCP starting...")

    # NOTE: BlenderMCPPreferences is now registered by __init__.py
    # to guarantee correct bl_idname in Blender Extension mode.
    
    # 1. Modular registration of UI and Core components
    try:
        from .addon.core.registration import register_all
        register_all()
    except (ImportError, ValueError):
        # Fallback for manual registration if core is not found
        for cls in _UI_CLASSES:
            bpy.utils.register_class(cls)

    # 2. Setup Scene properties (Global context)
    bpy.types.Scene.blendermcp_server_running = bpy.props.BoolProperty(name="Server Running", default=False)
    bpy.types.Scene.blendermcp_port = bpy.props.IntProperty(name="Port", default=9876)
    bpy.types.Scene.blendermcp_chat_prompt = bpy.props.StringProperty(name="Ask AI", default="")
    bpy.types.Scene.blendermcp_chat_status = bpy.props.StringProperty(name="AI Status", default="Ready")
    # Action metrics & UX
    bpy.types.Scene.blendermcp_last_action = bpy.props.StringProperty(name="Last Action", default="None")
    bpy.types.Scene.blendermcp_last_action_at = bpy.props.StringProperty(name="At", default="")
    bpy.types.Scene.blendermcp_last_action_details = bpy.props.StringProperty(name="Details", default="")
    bpy.types.Scene.blendermcp_last_action_ok = bpy.props.BoolProperty(name="Status", default=True)

    # Part Preset System
    from .addon.handlers.functional_parts import get_preset_items, get_role_items
    bpy.types.Scene.blendermcp_part_preset = bpy.props.EnumProperty(
        name="Part Preset",
        description="Select a project type to define available part roles",
        items=get_preset_items,
    )
    bpy.types.Scene.blendermcp_part_role = bpy.props.EnumProperty(
        name="Part Role",
        description="Role to assign to the selected object",
        items=get_role_items,
    )

    print(f"BlenderMCP v2.8.0 registered. (package={_ADDON_PACKAGE})")



def unregister():
    # 1. Stop the server
    if hasattr(bpy.types, "blendermcp_server") and bpy.types.blendermcp_server:
        bpy.types.blendermcp_server.stop()
        del bpy.types.blendermcp_server

    # 2. Call modular unregistration
    try:
        from .addon.core.registration import unregister_all
        unregister_all()
    except (ImportError, ValueError):
        # Fallback cleanup
        for cls in reversed(_UI_CLASSES):
            try:
                if hasattr(cls, "bl_rna"):
                    bpy.utils.unregister_class(cls)
            except Exception: pass
        
        mcp_props = [p for p in dir(bpy.types.Scene) if p.startswith("blendermcp_")]
        for prop in mcp_props:
            try: delattr(bpy.types.Scene, prop)
            except Exception: pass

    # NOTE: BlenderMCPPreferences is unregistered by __init__.py

    print("BlenderMCP v2.8.0 unregistered.")


if __name__ == "__main__":
    register()
