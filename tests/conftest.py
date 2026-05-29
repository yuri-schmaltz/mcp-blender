import sys
from unittest.mock import MagicMock

# Setup mock modules for Blender's bpy and mathutils during host tests
mock_bpy = MagicMock()
mock_bpy.props.BoolProperty = MagicMock(return_value=None)
mock_bpy.props.EnumProperty = MagicMock(return_value=None)
mock_bpy.props.IntProperty = MagicMock(return_value=None)
mock_bpy.props.StringProperty = MagicMock(return_value=None)
mock_bpy.props.FloatProperty = MagicMock(return_value=None)
mock_bpy.props.PointerProperty = MagicMock(return_value=None)
mock_bpy.props.CollectionProperty = MagicMock(return_value=None)

sys.modules["bpy"] = mock_bpy
sys.modules["bpy.props"] = mock_bpy.props
sys.modules["bpy.types"] = mock_bpy.types
sys.modules["bpy.ops"] = mock_bpy.ops
sys.modules["bpy.app"] = mock_bpy.app
sys.modules["mathutils"] = MagicMock()
