"""Studio and rendering tools for BlenderMCP."""

import bpy
import os
import math

def setup_product_studio(scene, theme='CLEAN'):
    """Setup a professional studio environment (piso infinito, lights)."""
    try:
        # 1. Create Cyclorama (Infinite floor)
        if "Studio_Cyclorama" not in scene.objects:
            bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
            cyc = bpy.context.active_object
            cyc.name = "Studio_Cyclorama"
            
            # Just create a Large plane and a Background Wall
            bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 10, 10), rotation=(math.radians(90), 0, 0))
            wall = bpy.context.active_object
            wall.name = "Studio_Wall"
            wall.parent = cyc

        # 2. Three-Point Lighting
        lights = ["Key_Light", "Fill_Light", "Back_Light"]
        for l_name in lights:
            if l_name in scene.objects:
                bpy.data.objects.remove(scene.objects[l_name], do_unlink=True)
                
        # Key Light
        bpy.ops.object.light_add(type='AREA', location=(5, -5, 5))
        key = bpy.context.active_object
        key.name = "Key_Light"
        key.data.energy = 500
        key.scale = (2, 2, 2)
        
        # Fill Light
        bpy.ops.object.light_add(type='AREA', location=(-5, -3, 3))
        fill = bpy.context.active_object
        fill.name = "Fill_Light"
        fill.data.energy = 200
        fill.scale = (3, 3, 3)
        
        # Back Light
        bpy.ops.object.light_add(type='AREA', location=(0, 5, 5))
        back = bpy.context.active_object
        back.name = "Back_Light"
        back.data.energy = 300
        
        # 3. Camera Setup
        if "Studio_Camera" not in scene.objects:
            bpy.ops.object.camera_add(location=(0, -10, 3), rotation=(math.radians(80), 0, 0))
            cam = bpy.context.active_object
            cam.name = "Studio_Camera"
            scene.camera = cam

        return {"success": True, "message": f"Studio '{theme}' setup complete with 3-point lighting."}
    except Exception as e:
        return {"error": f"Failed to setup studio: {str(e)}"}

def render_catalog_angles(scene, output_dir=None):
    """Render the model from 4 standard catalog angles."""
    try:
        if not output_dir:
            output_dir = os.path.join(os.path.expanduser("~"), "blender_mcp_catalog")
        
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        cam = scene.objects.get("Studio_Camera")
        if not cam:
            return {"error": "Studio_Camera not found. Run setup_product_studio first."}
            
        angles = {
            "front": (0, -10, 2),
            "side": (-10, 0, 2),
            "perspective": (-7, -7, 4),
            "top": (0, 0, 15)
        }
        
        renders = []
        for name, loc in angles.items():
            cam.location = loc
            # Look at center
            # Using simple constraint or tracking logic
            filepath = os.path.join(output_dir, f"catalog_{name}.png")
            scene.render.filepath = filepath
            bpy.ops.render.render(write_still=True)
            renders.append(filepath)
            
        return {"success": True, "message": f"Rendered {len(renders)} angles to {output_dir}", "files": renders}
    except Exception as e:
        return {"error": f"Failed to render catalog: {str(e)}"}
