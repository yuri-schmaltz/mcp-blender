"""Fundamental modeling operations for BlenderMCP.
Wraps common bpy.ops.mesh.* operators with semantic names for LLM tool calling.
"""
import math
import bpy
import bmesh
from ..core.router import mcp_command


@mcp_command(name="extrude_faces", read_only=False)
def extrude_faces(scene, name, amount=1.0, select_all=True):
    """Extrude faces of a mesh along their normals."""
    try:
        obj = scene.objects.get(name)
        if not obj or obj.type != 'MESH':
            return {"error": f"Mesh object '{name}' not found."}

        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')

        if select_all:
            bpy.ops.mesh.select_all(action='SELECT')

        bpy.ops.mesh.extrude_region_shrink_fatten(
            TRANSFORM_OT_shrink_fatten={"value": amount}
        )
        bpy.ops.object.mode_set(mode='OBJECT')

        return {"success": True, "message": f"Extruded faces of '{name}' by {amount}."}
    except Exception as e:
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"error": str(e)}


@mcp_command(name="inset_faces", read_only=False)
def inset_faces(scene, name, thickness=0.1, depth=0.0, select_all=True):
    """Create an inset on faces of a mesh."""
    try:
        obj = scene.objects.get(name)
        if not obj or obj.type != 'MESH':
            return {"error": f"Mesh object '{name}' not found."}

        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')

        if select_all:
            bpy.ops.mesh.select_all(action='SELECT')

        bpy.ops.mesh.inset(thickness=thickness, depth=depth)
        bpy.ops.object.mode_set(mode='OBJECT')

        return {"success": True, "message": f"Inset faces of '{name}' (thickness={thickness}, depth={depth})."}
    except Exception as e:
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"error": str(e)}


@mcp_command(name="bevel_edges", read_only=False)
def bevel_edges(scene, name, width=0.1, segments=1, profile=0.5, select_all=True):
    """Apply bevel to edges of a mesh."""
    try:
        obj = scene.objects.get(name)
        if not obj or obj.type != 'MESH':
            return {"error": f"Mesh object '{name}' not found."}

        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='EDGE')

        if select_all:
            bpy.ops.mesh.select_all(action='SELECT')

        bpy.ops.mesh.bevel(offset=width, segments=segments, profile=profile)
        bpy.ops.object.mode_set(mode='OBJECT')

        return {"success": True, "message": f"Beveled edges of '{name}' (width={width}, segments={segments})."}
    except Exception as e:
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"error": str(e)}


@mcp_command(name="subdivide_mesh", read_only=False)
def subdivide_mesh(scene, name, number_cuts=1, smoothness=0.0):
    """Subdivide a mesh."""
    try:
        obj = scene.objects.get(name)
        if not obj or obj.type != 'MESH':
            return {"error": f"Mesh object '{name}' not found."}

        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.subdivide(number_cuts=number_cuts, smoothness=smoothness)
        bpy.ops.object.mode_set(mode='OBJECT')

        verts = len(obj.data.vertices)
        faces = len(obj.data.polygons)
        return {"success": True, "message": f"Subdivided '{name}' ({number_cuts} cuts). Now {verts} verts, {faces} faces."}
    except Exception as e:
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"error": str(e)}


@mcp_command(name="merge_vertices", read_only=False)
def merge_vertices(scene, name, threshold=0.0001):
    """Merge vertices by distance (remove doubles)."""
    try:
        obj = scene.objects.get(name)
        if not obj or obj.type != 'MESH':
            return {"error": f"Mesh object '{name}' not found."}

        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')

        initial_verts = len(obj.data.vertices)
        bpy.ops.mesh.remove_doubles(threshold=threshold)
        bpy.ops.object.mode_set(mode='OBJECT')
        final_verts = len(obj.data.vertices)
        removed = initial_verts - final_verts

        return {"success": True, "message": f"Merged vertices on '{name}'. Removed {removed} duplicates (threshold={threshold})."}
    except Exception as e:
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"error": str(e)}


@mcp_command(name="fill_hole", read_only=False)
def fill_hole(scene, name, method="BEAUTY"):
    """Fill holes in a mesh by selecting non-manifold edges and filling."""
    try:
        obj = scene.objects.get(name)
        if not obj or obj.type != 'MESH':
            return {"error": f"Mesh object '{name}' not found."}

        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')

        # Select non-manifold edges (boundaries = holes)
        bpy.ops.mesh.select_non_manifold(extend=False)
        bpy.ops.mesh.fill()

        if method == "BEAUTY":
            bpy.ops.mesh.beautify_fill()

        bpy.ops.object.mode_set(mode='OBJECT')
        return {"success": True, "message": f"Filled holes in '{name}' using {method} method."}
    except Exception as e:
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"error": str(e)}


@mcp_command(name="spin_mesh", read_only=False)
def spin_mesh(scene, name, axis="Z", angle=360, steps=32):
    """Create rotational geometry by spinning a mesh profile around an axis."""
    try:
        obj = scene.objects.get(name)
        if not obj or obj.type != 'MESH':
            return {"error": f"Mesh object '{name}' not found."}

        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')

        axis_map = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}
        axis_vec = axis_map.get(axis.upper(), (0, 0, 1))

        bpy.ops.mesh.spin(
            steps=steps,
            angle=math.radians(angle),
            axis=axis_vec,
            center=obj.location
        )
        bpy.ops.object.mode_set(mode='OBJECT')

        return {"success": True, "message": f"Spun '{name}' {angle}° around {axis} in {steps} steps."}
    except Exception as e:
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"error": str(e)}


@mcp_command(name="recalculate_normals", read_only=False)
def recalculate_normals(scene, name, inside=False):
    """Recalculate mesh normals to point outward (or inward)."""
    try:
        obj = scene.objects.get(name)
        if not obj or obj.type != 'MESH':
            return {"error": f"Mesh object '{name}' not found."}

        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')

        if inside:
            bpy.ops.mesh.flip_normals()
        else:
            bpy.ops.mesh.normals_make_consistent(inside=False)

        bpy.ops.object.mode_set(mode='OBJECT')
        direction = "inward" if inside else "outward"
        return {"success": True, "message": f"Recalculated normals of '{name}' to face {direction}."}
    except Exception as e:
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"error": str(e)}


@mcp_command(name="mark_sharp_by_angle", read_only=False)
def mark_sharp_by_angle(scene, name, angle=30.0):
    """Mark edges as sharp based on face angle threshold."""
    try:
        obj = scene.objects.get(name)
        if not obj or obj.type != 'MESH':
            return {"error": f"Mesh object '{name}' not found."}

        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.edges_select_sharp(sharpness=math.radians(angle))
        bpy.ops.mesh.mark_sharp()
        bpy.ops.object.mode_set(mode='OBJECT')

        return {"success": True, "message": f"Marked sharp edges on '{name}' (angle > {angle}°)."}
    except Exception as e:
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"error": str(e)}
