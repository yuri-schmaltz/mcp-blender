"""Smart modifier shortcuts and mesh cleanup tools for BlenderMCP."""

import math

import bpy

from ..core.router import mcp_command


@mcp_command(name="add_modifier", read_only=False)
def add_modifier(scene, name, modifier_type, properties=None):
    """Add any modifier to an object by type name and optionally set properties."""
    try:
        obj = scene.objects.get(name)
        if not obj:
            return {"error": f"Object '{name}' not found."}

        mod = obj.modifiers.new(name=modifier_type, type=modifier_type)
        if properties and isinstance(properties, dict):
            for key, value in properties.items():
                if hasattr(mod, key):
                    setattr(mod, key, value)

        return {
            "success": True,
            "message": f"Added {modifier_type} modifier to '{name}'.",
            "modifier_name": mod.name,
        }
    except Exception as e:
        return {"error": str(e)}


@mcp_command(name="apply_modifier", read_only=False)
def apply_modifier(scene, name, modifier_name):
    """Apply a specific modifier, making its effect permanent."""
    try:
        obj = scene.objects.get(name)
        if not obj:
            return {"error": f"Object '{name}' not found."}
        if modifier_name not in obj.modifiers:
            return {"error": f"Modifier '{modifier_name}' not found on '{name}'."}

        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=modifier_name)

        return {"success": True, "message": f"Applied modifier '{modifier_name}' on '{name}'."}
    except Exception as e:
        return {"error": str(e)}


@mcp_command(name="apply_all_modifiers", read_only=False)
def apply_all_modifiers(scene, name):
    """Apply all modifiers on an object at once."""
    try:
        obj = scene.objects.get(name)
        if not obj:
            return {"error": f"Object '{name}' not found."}

        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj

        applied = []
        for mod in list(obj.modifiers):
            try:
                bpy.ops.object.modifier_apply(modifier=mod.name)
                applied.append(mod.name)
            except Exception:
                pass  # Some modifiers can't be applied (e.g., on multi-user data)

        return {
            "success": True,
            "message": f"Applied {len(applied)} modifiers on '{name}'.",
            "applied": applied,
        }
    except Exception as e:
        return {"error": str(e)}


@mcp_command(name="add_mirror_modifier", read_only=False)
def add_mirror_modifier(scene, name, axis="X", use_clipping=True):
    """Add a mirror modifier with clipping enabled."""
    try:
        obj = scene.objects.get(name)
        if not obj:
            return {"error": f"Object '{name}' not found."}

        mod = obj.modifiers.new(name="Mirror", type="MIRROR")
        mod.use_clip = use_clipping

        # Reset all axes, then enable the requested one
        mod.use_axis[0] = "X" in axis.upper()
        mod.use_axis[1] = "Y" in axis.upper()
        mod.use_axis[2] = "Z" in axis.upper()

        return {
            "success": True,
            "message": f"Added Mirror modifier to '{name}' on axis {axis} (clipping={use_clipping}).",
        }
    except Exception as e:
        return {"error": str(e)}


@mcp_command(name="add_array_modifier", read_only=False)
def add_array_modifier(scene, name, count=3, offset=(1.0, 0.0, 0.0), use_relative=True):
    """Add an array modifier for linear duplication."""
    try:
        obj = scene.objects.get(name)
        if not obj:
            return {"error": f"Object '{name}' not found."}

        mod = obj.modifiers.new(name="Array", type="ARRAY")
        mod.count = count
        mod.use_relative_offset = use_relative
        mod.use_constant_offset = not use_relative

        if use_relative:
            mod.relative_offset_displace = offset
        else:
            mod.constant_offset_displace = offset

        return {"success": True, "message": f"Added Array modifier to '{name}' ({count} copies)."}
    except Exception as e:
        return {"error": str(e)}


@mcp_command(name="add_screw_modifier", read_only=False)
def add_screw_modifier(scene, name, axis="Z", angle=360, steps=32, screw_offset=0.0):
    """Add a Screw modifier for creating revolution geometry (vases, cups, screws)."""
    try:
        obj = scene.objects.get(name)
        if not obj:
            return {"error": f"Object '{name}' not found."}

        mod = obj.modifiers.new(name="Screw", type="SCREW")
        mod.axis = axis.upper()
        mod.angle = math.radians(angle)
        mod.steps = steps
        mod.render_steps = steps
        mod.screw_offset = screw_offset

        return {
            "success": True,
            "message": f"Added Screw modifier to '{name}' ({angle}° around {axis}).",
        }
    except Exception as e:
        return {"error": str(e)}


@mcp_command(name="add_curve_modifier", read_only=False)
def add_curve_modifier(scene, mesh_name, curve_name):
    """Deform a mesh along a curve using a Curve modifier."""
    try:
        obj = scene.objects.get(mesh_name)
        if not obj:
            return {"error": f"Object '{mesh_name}' not found."}
        curve = scene.objects.get(curve_name)
        if not curve or curve.type != "CURVE":
            return {"error": f"Curve object '{curve_name}' not found."}

        mod = obj.modifiers.new(name="Curve", type="CURVE")
        mod.object = curve

        return {
            "success": True,
            "message": f"Added Curve modifier to '{mesh_name}' using curve '{curve_name}'.",
        }
    except Exception as e:
        return {"error": str(e)}


@mcp_command(name="decimate_mesh", read_only=False)
def decimate_mesh(scene, name, ratio=0.5, method="COLLAPSE"):
    """Reduce polygon count while preserving shape."""
    try:
        obj = scene.objects.get(name)
        if not obj or obj.type != "MESH":
            return {"error": f"Mesh object '{name}' not found."}

        initial_faces = len(obj.data.polygons)

        mod = obj.modifiers.new(name="Decimate", type="DECIMATE")
        if method == "COLLAPSE":
            mod.decimate_type = "COLLAPSE"
            mod.ratio = ratio
        elif method == "UNSUBDIV":
            mod.decimate_type = "UNSUBDIV"
            mod.iterations = max(1, int((1 - ratio) * 5))
        elif method == "PLANAR":
            mod.decimate_type = "DISSOLVE"
            mod.angle_limit = math.radians(5)

        # Apply immediately
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=mod.name)

        final_faces = len(obj.data.polygons)
        return {
            "success": True,
            "message": f"Decimated '{name}': {initial_faces} → {final_faces} faces ({method}, ratio={ratio}).",
        }
    except Exception as e:
        return {"error": str(e)}


@mcp_command(name="remesh_voxel", read_only=False)
def remesh_voxel(scene, name, voxel_size=0.1):
    """Remesh with voxels for uniform topology."""
    try:
        obj = scene.objects.get(name)
        if not obj or obj.type != "MESH":
            return {"error": f"Mesh object '{name}' not found."}

        mod = obj.modifiers.new(name="Remesh", type="REMESH")
        mod.mode = "VOXEL"
        mod.voxel_size = voxel_size

        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=mod.name)

        verts = len(obj.data.vertices)
        faces = len(obj.data.polygons)
        return {
            "success": True,
            "message": f"Voxel remeshed '{name}' (size={voxel_size}). Now {verts} verts, {faces} faces.",
        }
    except Exception as e:
        return {"error": str(e)}


@mcp_command(name="smooth_mesh", read_only=False)
def smooth_mesh(scene, name, iterations=10, factor=0.5):
    """Smooth a mesh using Laplacian smoothing."""
    try:
        obj = scene.objects.get(name)
        if not obj or obj.type != "MESH":
            return {"error": f"Mesh object '{name}' not found."}

        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")

        for _ in range(iterations):
            bpy.ops.mesh.vertices_smooth(factor=factor)

        bpy.ops.object.mode_set(mode="OBJECT")
        return {
            "success": True,
            "message": f"Smoothed '{name}' ({iterations} iterations, factor={factor}).",
        }
    except Exception as e:
        bpy.ops.object.mode_set(mode="OBJECT")
        return {"error": str(e)}


@mcp_command(name="shade_smooth", read_only=False)
def shade_smooth(scene, name, smooth=True):
    """Set smooth or flat shading on an object."""
    try:
        obj = scene.objects.get(name)
        if not obj or obj.type != "MESH":
            return {"error": f"Mesh object '{name}' not found."}

        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj

        if smooth:
            bpy.ops.object.shade_smooth()
        else:
            bpy.ops.object.shade_flat()

        mode = "smooth" if smooth else "flat"
        return {"success": True, "message": f"Set {mode} shading on '{name}'."}
    except Exception as e:
        return {"error": str(e)}
