"""BlenderMCP UI package - panels and operators."""

from .operators import OPERATOR_CLASSES
from .panel import PANEL_CLASSES

# All UI classes for Blender registration
UI_CLASSES = PANEL_CLASSES + OPERATOR_CLASSES

__all__ = ["UI_CLASSES", "OPERATOR_CLASSES", "PANEL_CLASSES"]
