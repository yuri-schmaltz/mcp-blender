"""Blender Extension entrypoint for Blender MCP."""
# ruff: noqa: N999

from __future__ import annotations

import importlib.util
from pathlib import Path


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
    spec.loader.exec_module(module)
    return module


bl_info = {
    "name": "Blender MCP",
    "author": "BlenderMCP",
    "version": (2, 4, 0),

    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > BlenderMCP",
    "description": "Connect Blender to local LLM clients via MCP",
    "category": "Interface",
}

# Cache the loaded module to avoid re-executing on unregister
_addon_mod = None


def register():
    global _addon_mod
    _addon_mod = _load_addon_module()
    _addon_mod.register()


def unregister():
    global _addon_mod
    if _addon_mod is None:
        _addon_mod = _load_addon_module()
    _addon_mod.unregister()


__all__ = ["bl_info", "register", "unregister"]


if __name__ == "__main__":
    register()
