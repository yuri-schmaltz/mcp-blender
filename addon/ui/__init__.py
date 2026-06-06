"""BlenderMCP UI package - panels and operators."""

import importlib.util
import os

# Load submodules via filesystem to work in all Blender loading modes.
_ui_dir = os.path.dirname(os.path.abspath(__file__))


from . import operators, panel

_operators_mod = operators
_panel_mod = panel

OPERATOR_CLASSES = _operators_mod.OPERATOR_CLASSES
PANEL_CLASSES = _panel_mod.PANEL_CLASSES

# All UI classes for Blender registration
UI_CLASSES = OPERATOR_CLASSES + PANEL_CLASSES

__all__ = ["UI_CLASSES", "OPERATOR_CLASSES", "PANEL_CLASSES"]
