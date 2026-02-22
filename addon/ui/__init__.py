"""BlenderMCP UI package - panels and operators."""

import importlib.util
import os

# Load submodules via filesystem to work in all Blender loading modes.
_ui_dir = os.path.dirname(os.path.abspath(__file__))


def _load_module(name, filename):
    path = os.path.join(_ui_dir, filename)
    spec = importlib.util.spec_from_file_location(f"_blendermcp_ui_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_operators_mod = _load_module("operators", "operators.py")
_panel_mod = _load_module("panel", "panel.py")

OPERATOR_CLASSES = _operators_mod.OPERATOR_CLASSES
PANEL_CLASSES = _panel_mod.PANEL_CLASSES

# All UI classes for Blender registration
UI_CLASSES = PANEL_CLASSES + OPERATOR_CLASSES

__all__ = ["UI_CLASSES", "OPERATOR_CLASSES", "PANEL_CLASSES"]
