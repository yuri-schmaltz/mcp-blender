"""Scene organization and utility tools for BlenderMCP."""
import bpy
from ..core.router import mcp_command


@mcp_command(name="duplicate_object", read_only=False)
def duplicate_object(scene, name, linked=False, offset=(0, 0, 0)):
    """Duplicate an object with optional offset."""
    try:
        obj = scene.objects.get(name)
        if not obj:
            return {"error": f"Object '{name}' not found."}

        new_obj = obj.copy()
        if not linked and obj.data:
            new_obj.data = obj.data.copy()
        scene.collection.objects.link(new_obj)
        new_obj.location.x += offset[0]
        new_obj.location.y += offset[1]
        new_obj.location.z += offset[2]

        return {"success": True, "message": f"Duplicated '{name}' as '{new_obj.name}'.", "new_name": new_obj.name}
    except Exception as e:
        return {"error": str(e)}


@mcp_command(name="join_objects", read_only=False)
def join_objects(scene, object_names):
    """Join multiple mesh objects into one."""
    try:
        bpy.ops.object.select_all(action='DESELECT')
        target = None
        for n in object_names:
            obj = scene.objects.get(n)
            if obj and obj.type == 'MESH':
                obj.select_set(True)
                if target is None:
                    target = obj

        if not target:
            return {"error": "No valid mesh objects found."}

        bpy.context.view_layer.objects.active = target
        bpy.ops.object.join()

        return {"success": True, "message": f"Joined {len(object_names)} objects into '{target.name}'.", "name": target.name}
    except Exception as e:
        return {"error": str(e)}


@mcp_command(name="create_collection", read_only=False)
def create_collection(scene, collection_name, object_names=None):
    """Create a new collection and optionally move objects into it."""
    try:
        col = bpy.data.collections.new(collection_name)
        scene.collection.children.link(col)

        moved = []
        if object_names:
            for n in object_names:
                obj = scene.objects.get(n)
                if obj:
                    # Unlink from current collections
                    for c in obj.users_collection:
                        c.objects.unlink(obj)
                    col.objects.link(obj)
                    moved.append(n)

        return {"success": True, "message": f"Created collection '{collection_name}'. Moved {len(moved)} objects.", "moved": moved}
    except Exception as e:
        return {"error": str(e)}


@mcp_command(name="move_to_collection", read_only=False)
def move_to_collection(scene, object_names, collection_name):
    """Move objects to an existing collection."""
    try:
        col = bpy.data.collections.get(collection_name)
        if not col:
            return {"error": f"Collection '{collection_name}' not found."}

        moved = []
        for n in object_names:
            obj = scene.objects.get(n)
            if obj:
                for c in obj.users_collection:
                    c.objects.unlink(obj)
                col.objects.link(obj)
                moved.append(n)

        return {"success": True, "message": f"Moved {len(moved)} objects to '{collection_name}'.", "moved": moved}
    except Exception as e:
        return {"error": str(e)}


@mcp_command(name="parent_objects", read_only=False)
def parent_objects(scene, parent_name, child_names):
    """Set parent-child relationship between objects."""
    try:
        parent = scene.objects.get(parent_name)
        if not parent:
            return {"error": f"Parent '{parent_name}' not found."}

        parented = []
        for n in child_names:
            child = scene.objects.get(n)
            if child:
                child.parent = parent
                child.matrix_parent_inverse = parent.matrix_world.inverted()
                parented.append(n)

        return {"success": True, "message": f"Parented {len(parented)} objects to '{parent_name}'.", "children": parented}
    except Exception as e:
        return {"error": str(e)}


@mcp_command(name="align_objects", read_only=False)
def align_objects(scene, object_names, axis="X", align_to="CENTER"):
    """Align multiple objects along an axis."""
    try:
        objects = [scene.objects.get(n) for n in object_names if scene.objects.get(n)]
        if len(objects) < 2:
            return {"error": "Need at least 2 objects to align."}

        axis_idx = {"X": 0, "Y": 1, "Z": 2}.get(axis.upper(), 0)

        if align_to == "CENTER":
            avg = sum(o.location[axis_idx] for o in objects) / len(objects)
        elif align_to == "MIN":
            avg = min(o.location[axis_idx] for o in objects)
        elif align_to == "MAX":
            avg = max(o.location[axis_idx] for o in objects)
        else:
            avg = 0

        for obj in objects:
            obj.location[axis_idx] = avg

        return {"success": True, "message": f"Aligned {len(objects)} objects on {axis} axis to {align_to}."}
    except Exception as e:
        return {"error": str(e)}


@mcp_command(name="distribute_objects", read_only=False)
def distribute_objects(scene, object_names, axis="X", spacing=2.0):
    """Distribute objects evenly along an axis."""
    try:
        objects = [scene.objects.get(n) for n in object_names if scene.objects.get(n)]
        if len(objects) < 2:
            return {"error": "Need at least 2 objects to distribute."}

        axis_idx = {"X": 0, "Y": 1, "Z": 2}.get(axis.upper(), 0)

        # Sort by current position
        objects.sort(key=lambda o: o.location[axis_idx])
        start = objects[0].location[axis_idx]

        for i, obj in enumerate(objects):
            obj.location[axis_idx] = start + (i * spacing)

        return {"success": True, "message": f"Distributed {len(objects)} objects along {axis} with {spacing} spacing."}
    except Exception as e:
        return {"error": str(e)}


@mcp_command(name="smart_uv_project", read_only=False)
def smart_uv_project(scene, name, angle_limit=66.0, island_margin=0.02):
    """Unwrap UVs using Smart UV Project."""
    try:
        obj = scene.objects.get(name)
        if not obj or obj.type != 'MESH':
            return {"error": f"Mesh object '{name}' not found."}

        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project(angle_limit=angle_limit, island_margin=island_margin)
        bpy.ops.object.mode_set(mode='OBJECT')

        return {"success": True, "message": f"Smart UV projected '{name}' (angle={angle_limit}°, margin={island_margin})."}
    except Exception as e:
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"error": str(e)}


@mcp_command(name="text_to_mesh", read_only=False)
def text_to_mesh(scene, text, size=1.0, extrude=0.1, bevel_depth=0.01, font=None, convert=True):
    """Create 3D text and optionally convert to mesh."""
    try:
        bpy.ops.object.text_add()
        obj = bpy.context.active_object
        obj.data.body = text
        obj.data.size = size
        obj.data.extrude = extrude
        obj.data.bevel_depth = bevel_depth

        if font and font in bpy.data.fonts:
            obj.data.font = bpy.data.fonts[font]

        if convert:
            bpy.ops.object.convert(target='MESH')

        return {"success": True, "message": f"Created 3D text '{text}' (size={size}, extrude={extrude}).", "name": obj.name}
    except Exception as e:
        return {"error": str(e)}


@mcp_command(name="separate_by_material", read_only=False)
def separate_by_material(scene, name):
    """Separate a mesh into individual objects by material slot."""
    try:
        obj = scene.objects.get(name)
        if not obj or obj.type != 'MESH':
            return {"error": f"Mesh object '{name}' not found."}

        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.separate(type='MATERIAL')
        bpy.ops.object.mode_set(mode='OBJECT')

        return {"success": True, "message": f"Separated '{name}' by material."}
    except Exception as e:
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"error": str(e)}
