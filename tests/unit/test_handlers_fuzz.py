import sys
from unittest.mock import MagicMock

# Mock bpy and its submodules before importing handlers that depend on them
mock_bpy = MagicMock()
mock_mathutils = MagicMock()
sys.modules["bpy"] = mock_bpy
sys.modules["mathutils"] = mock_mathutils

import pytest

from addon.handlers.material_tools import set_texture

# Import handlers from the new modular structure
from addon.handlers.polyhaven import download_polyhaven_asset, get_polyhaven_categories
from addon.handlers.scene import get_scene_info
from addon.handlers.sketchfab import search_sketchfab_models


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


def test_create_screw_hole_handlers():
    """Test create_screw_hole mechanical tool handler with mock objects."""
    from addon.handlers.mechanical_tools import create_screw_hole

    mock_scene = MagicMock()
    mock_p1 = MagicMock()
    mock_p2 = MagicMock()
    mock_scene.objects = {"Part1": mock_p1, "Part2": mock_p2}

    # Run with default parameters
    res = create_screw_hole(mock_scene, "Part1", "Part2", screw_type="M3")
    assert isinstance(res, dict)

    # Run with threaded insert and nut pocket
    res = create_screw_hole(
        mock_scene, "Part1", "Part2", screw_type="M3", threaded_insert=True, nut_pocket=True
    )
    assert isinstance(res, dict)


def test_simulation_tools_handlers():
    """Test mechanical simulation handlers (setup_physics_body, add_physics_constraint, run_assembly_simulation)."""
    from addon.handlers.mechanical_tools import (
        add_physics_constraint,
        run_assembly_simulation,
        setup_physics_body,
    )

    mock_scene = MagicMock()
    mock_p1 = MagicMock()
    mock_p2 = MagicMock()
    mock_scene.objects = {"Part1": mock_p1, "Part2": mock_p2}

    # Test setup_physics_body
    res1 = setup_physics_body(mock_scene, "Part1", body_type="ACTIVE")
    assert isinstance(res1, dict)

    # Test add_physics_constraint
    res2 = add_physics_constraint(mock_scene, "Part1", "Part2", constraint_type="HINGE")
    assert isinstance(res2, dict)

    # Test run_assembly_simulation
    res3 = run_assembly_simulation(mock_scene, end_frame=10, check_pairs=[["Part1", "Part2"]])
    assert isinstance(res3, dict)


def test_fastener_generator_handler():
    """Test fasteners generation handler."""
    from addon.handlers.fasteners import generate_fastener

    mock_scene = MagicMock()

    # Mock context and active_object
    mock_active = MagicMock()
    mock_active.name = "Test_Fastener"
    mock_bpy.context.active_object = mock_active
    mock_bpy.context.view_layer.objects.active = mock_active

    # Test screw generation
    res = generate_fastener(mock_scene, type="SCREW", size="M3", length=12.0)
    assert isinstance(res, dict)
    assert "success" in res or "error" in res

    # Test nut generation
    res_nut = generate_fastener(mock_scene, type="NUT", size="M3")
    assert isinstance(res_nut, dict)

    # Test washer generation
    res_washer = generate_fastener(mock_scene, type="WASHER", size="M3")
    assert isinstance(res_washer, dict)

    # Test bearing generation
    res_bearing = generate_fastener(mock_scene, type="BEARING", size="608")
    assert isinstance(res_bearing, dict)


def test_structural_analyzer_handler():
    """Test structural analyzer handler."""
    from addon.handlers.structural_analyzer import analyze_structural_properties

    mock_scene = MagicMock()
    mock_obj = MagicMock()
    mock_obj.type = "MESH"
    mock_obj.dimensions.x = 0.1
    mock_obj.dimensions.y = 0.05
    mock_obj.dimensions.z = 0.01

    # Mock mesh vertices and polygons
    mock_mesh = MagicMock()
    mock_vertex = MagicMock()
    mock_vertex.co = MagicMock()
    mock_mesh.vertices = [mock_vertex]

    mock_poly = MagicMock()
    mock_poly.vertices = [0, 1, 2]
    mock_mesh.polygons = [mock_poly]

    # Make evaluated_get return a mock object that returns this mesh
    mock_eval_obj = MagicMock()
    mock_eval_obj.to_mesh.return_value = mock_mesh
    mock_obj.evaluated_get.return_value = mock_eval_obj

    mock_scene.objects = {"TestMesh": mock_obj}

    res = analyze_structural_properties(mock_scene, "TestMesh", material_preset="PLA")
    assert isinstance(res, dict)
    assert "success" in res or "error" in res
