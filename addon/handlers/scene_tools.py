"""Scene and render control tools for BlenderMCP."""

import bpy
import mathutils
import math

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
        return {"error": f"Failed to setup camera: {str(e)}"}
