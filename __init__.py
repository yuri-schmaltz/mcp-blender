"""Blender Extension entrypoint for Blender MCP."""
# ruff: noqa: N999

from __future__ import annotations

import importlib.util
import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    IntProperty,
    StringProperty,
)

_ollama_models_cache = []
_ollama_fetch_time = 0


def fetch_ollama_models_thread(base_url):
    global _ollama_models_cache, _ollama_fetch_time
    try:
        url = base_url.rstrip("/") + "/api/tags"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=1.0) as response:
            data = json.loads(response.read().decode())
            models = [(m["name"], m["name"], "") for m in data.get("models", [])]
            if models:
                _ollama_models_cache = models
                _ollama_fetch_time = time.time()
    except Exception:
        pass


def get_ollama_items(self, context):
    global _ollama_models_cache, _ollama_fetch_time

    base_url = self.llm_base_url if self.llm_base_url else "http://localhost:11434"

    # If cache empty, perform quick sync fetch
    if not _ollama_models_cache:
        try:
            with urllib.request.urlopen(base_url.rstrip("/") + "/api/tags", timeout=2) as response:
                data = json.load(response)
                _ollama_models_cache = [(m["name"], m["name"], "") for m in data.get("models", [])]
                _ollama_fetch_time = time.time()
        except Exception:
            pass

    # Refresh in background if stale (>60s)
    if time.time() - _ollama_fetch_time > 60:
        threading.Thread(target=fetch_ollama_models_thread, args=(base_url,), daemon=True).start()

    res = list(_ollama_models_cache)
    res.append(("MANUAL", "Type Manually...", ""))
    return res


_custom_models_cache = []
_custom_fetch_time = 0


def fetch_custom_models_thread(base_url):
    global _custom_models_cache, _custom_fetch_time
    try:
        url = base_url.rstrip("/") + "/models"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=1.0) as response:
            data = json.loads(response.read().decode())
            models = [(m["id"], m["id"], "") for m in data.get("data", [])]
            if models:
                _custom_models_cache = models
                _custom_fetch_time = time.time()
    except Exception:
        pass


def get_custom_items(self, context):
    global _custom_models_cache, _custom_fetch_time
    base_url = self.llm_base_url if self.llm_base_url else "http://localhost:1234/v1"

    if time.time() - _custom_fetch_time > 10:
        _custom_fetch_time = time.time()
        threading.Thread(target=fetch_custom_models_thread, args=(base_url,), daemon=True).start()

    res = list(_custom_models_cache)
    res.append(("MANUAL", "Type Manually...", ""))
    return res


class BlenderMCPPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    port: IntProperty(
        name="Default Port",
        description="Default port for the BlenderMCP socket server",
        default=9876,
        min=1024,
        max=65535,
    )

    webui_port: IntProperty(
        name="WebUI Port",
        description="Port for the embedded HTML WebUI server",
        default=8080,
        min=1024,
        max=65535,
    )

    allow_code_execution: BoolProperty(
        name="Allow Remote Code Execution",
        description="WARNING: Allows the LLM to execute arbitrary Python code. Enable only if you trust the requests",
        default=False,
    )

    sketchfab_api_key: StringProperty(
        name="Sketchfab API Key",
        subtype="PASSWORD",
        description="Global Sketchfab API key",
        default="",
    )

    blenderkit_api_key: StringProperty(
        name="BlenderKit API Token",
        subtype="PASSWORD",
        description="Global BlenderKit API token",
        default="",
    )

    client_target: EnumProperty(
        name="Target Client",
        items=[
            ("lm_studio", "LM Studio", "Local LLM via LM Studio"),
            ("ollama", "Ollama", "Local LLM via Ollama"),
            ("custom", "Custom", "Generic OpenAI-compatible API"),
        ],
        default="lm_studio",
    )

    llm_provider: EnumProperty(
        name="LLM Provider",
        items=[
            ("OLLAMA", "Ollama (Local)", "Use local Ollama instance"),
            ("CUSTOM", "Custom / LM Studio (Local)", "Use any OpenAI-compatible local API"),
        ],
        default="OLLAMA",
    )

    llm_model_ollama: EnumProperty(
        name="Ollama Model",
        description="Select an installed Ollama model",
        items=get_ollama_items,
    )

    llm_model_custom_enum: EnumProperty(
        name="LM Studio / Custom Model",
        description="Select an available model from the custom server",
        items=get_custom_items,
    )

    llm_model_custom: StringProperty(
        name="Manual Model Name",
        description="Type the model name (e.g., llama3, mistral, etc.)",
        default="llama3",
    )

    llm_base_url: StringProperty(
        name="Base URL",
        description="Base URL for local providers (e.g., http://localhost:11434 for Ollama, http://localhost:1234/v1 for LM Studio)",
        default="",
    )

    llm_api_key: StringProperty(
        name="API Key",
        subtype="PASSWORD",
        description="API Key for the selected LLM Provider",
        default="",
    )

    mcp_tool_profile: EnumProperty(
        name="MCP Tool Profile",
        description="Filter tools exposed to the AI client to optimize prompt context and speed",
        items=[
            ("ALL", "Full (All Tools)", "Expose all 73 tools to the AI"),
            ("MODELING", "Modeling & Layout", "Expose only essential and modeling/transform tools"),
            (
                "MATERIALS",
                "Materials & Studio",
                "Expose only PBR materials, textures, and studio lighting tools",
            ),
            (
                "PHYSICS",
                "Mechanics & Simulation",
                "Expose only rigid body, physics constraints, and joint simulation tools",
            ),
            (
                "PRINTING",
                "3D Printing & CAD",
                "Expose only mesh analysis, repair, and 3D printing tools",
            ),
        ],
        default="ALL",
    )

    # Integration Toggles
    use_polyhaven: BoolProperty(
        name="Use Poly Haven",
        description="Enable Poly Haven asset integration",
        default=False,
    )
    use_ambientcg: BoolProperty(
        name="Use AmbientCG",
        description="Enable AmbientCG asset integration",
        default=False,
    )
    use_sketchfab: BoolProperty(
        name="Use Sketchfab",
        description="Enable Sketchfab asset integration",
        default=False,
    )
    use_blenderkit: BoolProperty(
        name="Use BlenderKit",
        description="Enable BlenderKit asset integration",
        default=False,
    )

    def draw(self, context):
        layout = self.layout

        # Section: Connection
        box = layout.box()
        box.label(text="Server & Security", icon="SETTINGS")
        row = box.row()
        row.prop(self, "port")
        row.prop(self, "allow_code_execution", toggle=True)
        col = box.column()
        col.prop(self, "mcp_tool_profile")

        # Section: Embedded Chat Client
        box = layout.box()
        box.label(text="Built-in AI Client", icon="COMMUNITY")
        col = box.column(align=True)
        col.prop(self, "llm_provider")

        if self.llm_provider == "OLLAMA":
            col.prop(self, "llm_model_ollama", text="Model Name")
            if self.llm_model_ollama == "MANUAL":
                col.prop(self, "llm_model_custom")
            col.prop(self, "llm_base_url")
        elif self.llm_provider == "CUSTOM":
            col.prop(self, "llm_model_custom_enum", text="Model Name")
            if self.llm_model_custom_enum == "MANUAL":
                col.prop(self, "llm_model_custom")
            col.prop(self, "llm_base_url")
            col.prop(self, "llm_api_key", text="API Key (Optional)")

        col.prop(self, "webui_port")

        # Section: Integrations
        box = layout.box()
        box.label(text="Integrations", icon="WORLD")
        grid = box.grid_flow(columns=2, even_columns=True, even_rows=False, align=True)
        grid.prop(self, "use_polyhaven", text="Poly Haven", icon="IMAGE_DATA")
        grid.prop(self, "use_ambientcg", text="AmbientCG", icon="MATERIAL")
        grid.prop(self, "use_sketchfab", text="Sketchfab", icon="MESH_MONKEY")
        grid.prop(self, "use_blenderkit", text="BlenderKit", icon="IMAGE_DATA")

        box.separator()
        col = box.column(align=True)
        col.prop(self, "sketchfab_api_key")
        col.prop(self, "blenderkit_api_key")

        # Section: Setup & Maintenance
        box = layout.box()
        box.label(text="Setup & Maintenance", icon="TOOL_SETTINGS")

        col = box.column(align=True)
        col.operator("blendermcp.install_dependencies", text="Install Dependencies", icon="IMPORT")
        col.operator("blendermcp.health_check", text="Health Check", icon="CHECKMARK")

        box.separator()
        box.label(text="Advanced (Stdio / Terminal):", icon="CONSOLE")
        box.prop(self, "client_target")
        box.operator("blendermcp.copy_mcp_client_config")
        box.operator("blendermcp.run_mcp_terminal_server")

        box.separator()
        box.operator("blendermcp.open_logs", icon="TEXT")
        box.operator("blendermcp.clear_cache", icon="TRASH")


# =============================================================================
# Dynamic addon module loading
# =============================================================================
def _load_addon_module():
    """Load addon.py and ensure it has the correct package context for relative imports."""
    addon_path = Path(__file__).with_name("addon.py")
    # Use the current package name if available (Blender 4.2+ Extension mode)
    pkg = __package__ if __package__ else "blender_mcp"

    spec = importlib.util.spec_from_file_location(f"{pkg}.addon_entry", addon_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load addon module from {addon_path}")

    module = importlib.util.module_from_spec(spec)
    # Crucial: set __package__ so relative imports like 'from .addon import ...' work
    module.__package__ = pkg
    # Register in sys.modules so submodules (UI, operators) can find it
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bl_info = {
    "name": "Blender MCP",
    "author": "BlenderMCP",
    "version": (2, 11, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > BlenderMCP",
    "description": "Connect Blender to local LLM clients via MCP",
    "category": "Interface",
}

# Cache the loaded module to avoid re-executing on unregister
_addon_mod = None


def register():
    global _addon_mod

    # 1. Register Preferences FIRST from __init__.py (guaranteed correct __package__)
    bpy.utils.register_class(BlenderMCPPreferences)

    # 2. Load and register the rest of the addon
    print("BlenderMCP: Loading addon module...")
    _addon_mod = _load_addon_module()
    _addon_mod.register()


def unregister():
    global _addon_mod
    if _addon_mod is None:
        _addon_mod = _load_addon_module()
    _addon_mod.unregister()

    # Clean up WebUI server if running
    if hasattr(bpy.types, "blendermcp_webui_server") and bpy.types.blendermcp_webui_server:
        bpy.types.blendermcp_webui_server.stop()
        del bpy.types.blendermcp_webui_server

    # Unregister Preferences last
    if hasattr(BlenderMCPPreferences, "bl_rna"):
        bpy.utils.unregister_class(BlenderMCPPreferences)


__all__ = ["bl_info", "register", "unregister"]


if __name__ == "__main__":
    register()
