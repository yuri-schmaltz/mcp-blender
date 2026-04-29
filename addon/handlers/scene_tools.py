"""Scene and render control tools for BlenderMCP."""
from ..core.router import mcp_command


import math
import mathutils
import traceback
import io
from contextlib import redirect_stdout

import bpy


@mcp_command(name="configure_render_settings", read_only=False)
def configure_render_settings(scene, engine="BLENDER_EEVEE", resolution_x=1920, resolution_y=1080, samples=64, use_gpu=True, transparent_background=False):
    """Configure render settings like engine, resolution, samples, and device."""
    try:
        render = scene.render

        # Determine correct Eevee engine name based on Blender version
        if engine.upper() in ["EEVEE", "BLENDER_EEVEE"]:
            # Blender 4.2+ uses BLENDER_EEVEE_NEXT, older uses BLENDER_EEVEE
            if bpy.app.version >= (4, 2, 0):
                engine = "BLENDER_EEVEE_NEXT"
            else:
                engine = "BLENDER_EEVEE"

        if engine.upper() == "CYCLES":
            engine = "CYCLES"

        render.engine = engine

        # Resolution
        render.resolution_x = int(resolution_x)
        render.resolution_y = int(resolution_y)
        render.resolution_percentage = 100

        # Transparent background
        render.film_transparent = bool(transparent_background)

        # Engine specific settings
        if engine == "CYCLES":
            cycles = scene.cycles
            cycles.samples = int(samples)
            if use_gpu:
                cycles.device = 'GPU'

                # Make sure GPU compute is enabled in preferences
                prefs = bpy.context.preferences
                cprefs = prefs.addons['cycles'].preferences

                # Try to enable all available GPU devices (CUDA, OptiX, HIP, Metal, OneAPI)
                for compute_device_type in ('CUDA', 'OPTIX', 'HIP', 'METAL', 'ONEAPI'):
                    try:
                        cprefs.compute_device_type = compute_device_type
                        cprefs.get_devices()
                        for device in cprefs.devices:
                            if device.type != 'CPU':
                                device.use = True
                        break  # Found at least one working compute type
                    except Exception:
                        continue
            else:
                cycles.device = 'CPU'

        elif engine in ["BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"]:
            # Eevee uses different properties depending on version
            if hasattr(scene, "eevee"):
                eevee = scene.eevee
                if hasattr(eevee, "taa_render_samples"):
                    eevee.taa_render_samples = int(samples) # Legacy Eevee

        return {
            "success": True,
            "message": f"Render settings configured: Engine={engine}, Resolution={resolution_x}x{resolution_y}, Samples={samples}",
            "engine": engine,
            "resolution": [render.resolution_x, render.resolution_y]
        }
    except Exception as e:
        return {"error": f"Failed to configure render settings: {str(e)}"}


@mcp_command(name="setup_camera", read_only=False)
def setup_camera(scene, focus_object_name=None, location=(0, -10, 5), create_new=False):
    """Set up the active camera, optionally pointing it at a specific object."""
    try:
        # Determine which camera to use
        cam_obj = scene.camera

        if create_new or not cam_obj:
            # Create a new camera
            cam_data = bpy.data.cameras.new(name="Camera_MCP")
            cam_obj = bpy.data.objects.new("Camera_MCP", cam_data)
            scene.collection.objects.link(cam_obj)
            scene.camera = cam_obj

        # Set location
        cam_obj.location = location

        # Point to object if specified
        target_obj = None
        if focus_object_name:
            if focus_object_name in bpy.data.objects:
                target_obj = bpy.data.objects[focus_object_name]
            else:
                return {"error": f"Object '{focus_object_name}' not found."}

        if target_obj:
            # Calculate rotation to point at the target
            direction = target_obj.location - cam_obj.location
            # Point camera '-Z' towards target, with 'Y' up
            rot_quat = direction.to_track_quat('-Z', 'Y')
            cam_obj.rotation_euler = rot_quat.to_euler()
            msg = f"Camera '{cam_obj.name}' positioned at {location} looking at '{target_obj.name}'."
        else:
            # Just set rotation to default looking forward if no target
            cam_obj.rotation_euler = (math.radians(90), 0, 0)
            msg = f"Camera '{cam_obj.name}' positioned at {location} looking forward."

        return {
            "success": True,
            "message": msg,
            "camera_name": cam_obj.name,
            "is_active": (scene.camera == cam_obj)
        }
    except Exception as e:
        return {"error": f"Failed to set up camera: {str(e)}"}

@mcp_command(name="get_scene_info", read_only=True)
def get_scene_info(scene, filter_type=None, filter_name=None, limit=100):
    """Get information about the current Blender scene"""
    try:
        # Simplify the scene info to reduce data size
        scene_info = {
            "name": scene.name,
            "object_count": len(scene.objects),
            "objects": [],
            "materials_count": len(bpy.data.materials),
            "active_object": scene.objects.active.name if scene.objects.active else None
        }

        # Collect object information
        count = 0
        for obj in scene.objects:
            if filter_type and obj.type != filter_type:
                continue
            if filter_name and filter_name.lower() not in obj.name.lower():
                continue
                
            obj_info = {
                "name": obj.name,
                "type": obj.type,
                "location": [
                    round(float(obj.location.x), 2),
                    round(float(obj.location.y), 2),
                    round(float(obj.location.z), 2),
                ],
            }
            scene_info["objects"].append(obj_info)
            count += 1
            if count >= limit:
                break
        return scene_info
    except Exception as e:
        traceback.print_exc()
        return {"error": str(e)}

@mcp_command(name="get_active_object", read_only=False)
def get_active_object(scene):
    """Get the currently active object"""
    obj = bpy.context.view_layer.objects.active
    if obj:
        return {"name": obj.name, "type": obj.type}
    return {"name": None, "message": "No active object"}

@mcp_command(name="set_active_object", read_only=False)
def set_active_object(scene, name):
    """Set the active object by name"""
    try:
        obj = scene.objects.get(name)
        if not obj:
            return {"error": f"Object '{name}' not found."}
        
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        return {"success": True, "message": f"Object '{name}' is now active."}
    except Exception as e:
        return {"error": str(e)}


def _get_aabb(obj):
    """Returns the world-space axis-aligned bounding box (AABB) of an object."""
    if obj.type != "MESH":
        raise TypeError("Object must be a mesh")

    # Get the bounding box corners in local space
    local_bbox_corners = [mathutils.Vector(corner) for corner in obj.bound_box]

    # Convert to world coordinates
    world_bbox_corners = [obj.matrix_world @ corner for corner in local_bbox_corners]

    # Compute axis-aligned min/max coordinates
    min_corner = mathutils.Vector(map(min, zip(*world_bbox_corners)))
    max_corner = mathutils.Vector(map(max, zip(*world_bbox_corners)))

    return [[*min_corner], [*max_corner]]


@mcp_command(name="get_object_info", read_only=True)
def get_object_info(scene, name):
    """Get detailed information about a specific object"""
    obj = bpy.data.objects.get(name)
    if not obj:
        raise ValueError(f"Object not found: {name}")

    # Basic object info
    obj_info = {
        "name": obj.name,
        "type": obj.type,
        "location": [obj.location.x, obj.location.y, obj.location.z],
        "rotation": [obj.rotation_euler.x, obj.rotation_euler.y, obj.rotation_euler.z],
        "scale": [obj.scale.x, obj.scale.y, obj.scale.z],
        "visible": obj.visible_get(),
        "materials": [],
    }

    if obj.type == "MESH":
        obj_info["world_bounding_box"] = _get_aabb(obj)

    # Add material slots
    for slot in obj.material_slots:
        if slot.material:
            obj_info["materials"].append(slot.material.name)

    # Add mesh data if applicable
    if obj.type == "MESH" and obj.data:
        mesh = obj.data
        obj_info["mesh"] = {
            "vertices": len(mesh.vertices),
            "edges": len(mesh.edges),
            "polygons": len(mesh.polygons),
        }
    return obj_info

@mcp_command(name="get_viewport_screenshot", read_only=True)
def get_viewport_screenshot(scene, max_size=800, filepath=None, format="png"):
    """
    Capture a screenshot of the current 3D viewport and save it to the specified path.
    """
    try:
        if not filepath:
            return {"error": "No filepath provided"}

        # Find the active 3D viewport
        area = None
        for a in bpy.context.screen.areas:
            if a.type == "VIEW_3D":
                area = a
                break

        if not area:
            return {"error": "No 3D viewport found"}

        # Take screenshot with proper context override
        with bpy.context.temp_override(area=area):
            bpy.ops.screen.screenshot_area(filepath=filepath)

        # Load and resize if needed
        img = bpy.data.images.load(filepath)
        width, height = img.size

        if max(width, height) > max_size:
            scale = max_size / max(width, height)
            new_width = int(width * scale)
            new_height = int(height * scale)
            img.scale(new_width, new_height)

            # Set format and save
            img.file_format = format.upper()
            img.save()
            width, height = new_width, new_height

        # Cleanup Blender image data
        bpy.data.images.remove(img)

        return {"success": True, "width": width, "height": height, "filepath": filepath}

    except Exception as e:
        return {"error": str(e)}
