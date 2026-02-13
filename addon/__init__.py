"""BlenderMCP addon package compatibility entrypoint."""
# ruff: noqa: N999

from __future__ import annotations

import importlib.util
from pathlib import Path

__all__ = ["server", "handlers", "ui", "utils", "register", "unregister"]


def _load_legacy_addon_module():
    addon_path = Path(__file__).resolve().parent.parent / "addon.py"
    spec = importlib.util.spec_from_file_location("blender_mcp_addon_legacy", addon_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load addon module from {addon_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def register():
    _load_legacy_addon_module().register()


def unregister():
    _load_legacy_addon_module().unregister()
