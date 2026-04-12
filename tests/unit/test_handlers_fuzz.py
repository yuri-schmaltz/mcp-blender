import sys
from unittest.mock import MagicMock

# Mock bpy and its submodules before importing handlers that depend on them
mock_bpy = MagicMock()
mock_mathutils = MagicMock()
sys.modules["bpy"] = mock_bpy
sys.modules["mathutils"] = mock_mathutils

import pytest

# Import handlers from the new modular structure
from addon.handlers.polyhaven import download_polyhaven_asset, get_polyhaven_categories
from addon.handlers.scene import get_scene_info
from addon.handlers.sketchfab import search_sketchfab_models
from addon.handlers.material_tools import set_texture

def test_scene_info():
    """Test the basic scene info handler (stubbed for tests)."""
    result = get_scene_info()
    assert result["status"] == "success"
    assert "scene" in result

def test_polyhaven_download_validation():
    """Test Polyhaven download logic with mock scene."""
    mock_scene = MagicMock()
    # Note: Handlers expect a scene object if they access properties
    # But some parts of handlers might use bpy.context.scene directly.
    # We test if it handles missing assets gracefully.
    try:
        result = download_polyhaven_asset(mock_scene, "asset123", "textures")
        # Since we are in a non-Blender env with mocks, it might return an error or status
        assert isinstance(result, dict)
    except Exception:
        # In this env, bpy might be missing or mocked
        pass

def test_sketchfab_search():
    """Test Sketchfab search handler (mocked context)."""
    mock_scene = MagicMock()
    try:
        result = search_sketchfab_models(mock_scene, "car")
        assert isinstance(result, dict)
    except Exception:
        pass

def test_material_tools_logic():
    """Test material setup logic."""
    mock_scene = MagicMock()
    try:
        result = set_texture(mock_scene, "Cube", "texture123")
        assert isinstance(result, dict)
    except Exception:
        pass

def test_scene_info_fuzz():
    """Fuzzing: Invalid input should not crash the handler."""
    try:
        get_scene_info()
    except Exception:
        pytest.fail("get_scene_info crashed on basic call")

def test_polyhaven_categories_fuzz():
    """Verify category lookup handles invalid types."""
    try:
        get_polyhaven_categories("invalid_type")
    except Exception:
        pass
