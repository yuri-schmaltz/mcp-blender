import sys
from unittest.mock import MagicMock

# Mock bpy and its submodules for all tests run outside of Blender
class BpyMock(MagicMock):
    __path__ = []

mock_bpy = BpyMock()
sys.modules["bpy"] = mock_bpy
sys.modules["bpy.props"] = mock_bpy.props
sys.modules["bpy.types"] = mock_bpy.types
sys.modules["bpy.app"] = mock_bpy.app
sys.modules["bpy.app.timers"] = mock_bpy.app.timers
sys.modules["bpy.ops"] = mock_bpy.ops
sys.modules["mathutils"] = MagicMock()
