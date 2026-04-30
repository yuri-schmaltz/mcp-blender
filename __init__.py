"""Blender Extension entrypoint for Blender MCP."""
# ruff: noqa: N999

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    IntProperty,
    StringProperty,
)


# =============================================================================
# Addon Preferences – MUST live in __init__.py for Blender Extensions
# =============================================================================
class BlenderMCPPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    port: IntProperty(
        name="Default Port",
        description="Default port for the BlenderMCP socket server",
        default=9876,
        min=1024,
        max=65535,
    )

    allow_code_execution: BoolProperty(
        name="Allow Remote Code Execution",
        description="WARNING: Allows the LLM to execute arbitrary Python code. Enable only if you trust the requests",
        default=False,
    )

    # API Keys
    openai_key: StringProperty(
        name="OpenAI API Key",
        subtype="PASSWORD",
        description="Global OpenAI API key",
        default="",
    )

    anthropic_key: StringProperty(
        name="Anthropic API Key",
        subtype="PASSWORD",
        description="Global Anthropic API key",
        default="",
    )

    google_key: StringProperty(
        name="Google API Key",
        subtype="PASSWORD",
        description="Global Google Gemini API key",
        default="",
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

    # Online LLM Integration
    llm_provider: EnumProperty(
        name="Provider",
        description="Select the online LLM provider to use",
        items=[
            ("OPENAI", "OpenAI", "Use OpenAI models"),
            ("ANTHROPIC", "Anthropic", "Use Anthropic models"),
            ("GOOGLE", "Google", "Use Google Gemini models"),
        ],
        default="OPENAI",
    )

    openai_model: EnumProperty(
        name="OpenAI Model",
        items=[
            ("gpt-4o", "GPT-4o", ""),
            ("gpt-4o-mini", "GPT-4o Mini", ""),
            ("gpt-3.5-turbo", "GPT-3.5 Turbo", ""),
        ],
        default="gpt-4o",
    )

    anthropic_model: EnumProperty(
        name="Anthropic Model",
        items=[
            ("claude-3-5-sonnet-20240620", "Claude 3.5 Sonnet", ""),
            ("claude-3-opus-20240229", "Claude 3 Opus", ""),
            ("claude-3-haiku-20240307", "Claude 3 Haiku", ""),
        ],
        default="claude-3-5-sonnet-20240620",
    )

    google_model: EnumProperty(
        name="Google Model",
        items=[
            ("gemini-1.5-pro", "Gemini 1.5 Pro", ""),
            ("gemini-1.5-flash", "Gemini 1.5 Flash", ""),
        ],
        default="gemini-1.5-pro",
    )

    def draw(self, context):
        layout = self.layout

        # Section: Connection
        box = layout.box()
        box.label(text="Server & Security", icon="SETTINGS")
        row = box.row()
        row.prop(self, "port")
        row.prop(self, "allow_code_execution", toggle=True)

        # Section: Integrations
        box = layout.box()
        box.label(text="Integrations", icon="WORLD")
        grid = box.grid_flow(columns=2, even_columns=True, even_rows=False, align=True)
        grid.prop(self, "use_polyhaven", text="Poly Haven", icon="IMAGE_DATA")
        grid.prop(self, "use_ambientcg", text="AmbientCG", icon="MATERIAL")
        grid.prop(self, "use_sketchfab", text="Sketchfab", icon="MESH_MONKEY")
        grid.prop(self, "use_blenderkit", text="BlenderKit", icon="IMAGE_DATA")

        # Section: API Keys
        box = layout.box()
        box.label(text="API Keys & LLM Config", icon="CONSOLE")

        col = box.column(align=True)
        col.prop(self, "llm_provider")

        if self.llm_provider == 'OPENAI':
            col.prop(self, "openai_key")
            col.prop(self, "openai_model")
        elif self.llm_provider == 'ANTHROPIC':
            col.prop(self, "anthropic_key")
            col.prop(self, "anthropic_model")
        elif self.llm_provider == 'GOOGLE':
            col.prop(self, "google_key")
            col.prop(self, "google_model")

        box.separator()
        col = box.column(align=True)
        col.prop(self, "sketchfab_api_key")
        col.prop(self, "blenderkit_api_key")


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
    "version": (2, 6, 0),

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

    # Unregister Preferences last
    if hasattr(BlenderMCPPreferences, "bl_rna"):
        bpy.utils.unregister_class(BlenderMCPPreferences)


__all__ = ["bl_info", "register", "unregister"]


if __name__ == "__main__":
    register()
