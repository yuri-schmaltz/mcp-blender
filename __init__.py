"""Blender Extension entrypoint for Blender MCP."""
# ruff: noqa: N999

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_addon_module():
    """Always load addon.py via filesystem to avoid collision with addon/ directory."""
    addon_path = Path(__file__).with_name("addon.py")
    spec = importlib.util.spec_from_file_location("blender_mcp_addon_entry", addon_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load addon module from {addon_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bl_info = {
    "name": "Blender MCP",
    "author": "BlenderMCP",
    "version": (1, 8, 0),
    "blender": (3, 0, 0),
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
