"""Blender Extension entrypoint for Blender MCP."""
# ruff: noqa: N999

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path


def _load_addon_module():
    try:
        if __package__:
            return importlib.import_module(".addon", package=__package__)
    except Exception:
        pass

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
    "version": (1, 3, 4),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > BlenderMCP",
    "description": "Connect Blender to local LLM clients via MCP",
    "category": "Interface",
}


def register():
    _load_addon_module().register()


def unregister():
    _load_addon_module().unregister()

__all__ = ["bl_info", "register", "unregister"]


if __name__ == "__main__":
    register()
