"""Mechanical tools for BlenderMCP."""

import bpy
import mathutils
import math

def create_axle_joint(scene, chassis_name, wheel_name, axle_diameter=None, clearance=0.2, hole_depth=None):
    """Create a mechanical axle joint (hole in chassis, pin on wheel)."""
    try:
        if chassis_name not in scene.objects:
            return {"error": f"Chassis object '{chassis_name}' not found."}
        if wheel_name not in scene.objects:
            return {"error": f"Wheel object '{wheel_name}' not found."}
            
        chassis = scene.objects[chassis_name]
        wheel = scene.objects[wheel_name]
        
        if chassis.type != 'MESH' or wheel.type != 'MESH':
            return {"error": "Both objects must be of type MESH."}

        # Calculate wheel center and dimensions
        bpy.context.view_layer.update()
        bbox_corners = [wheel.matrix_world @ mathutils.Vector(corner) for corner in wheel.bound_box]
        center = sum(bbox_corners, mathutils.Vector()) / 8
        
        dims = wheel.dimensions
        # Guess axle axis: usually the shortest dimension for a wheel
        # Or based on major orientation. For vehicles, wheels usually span XZ or YZ.
        # We'll assume the axle is perpendicular to the circular face.
        if dims.x < dims.y and dims.x < dims.z:
            axle_axis = 'X'
            radius = (dims.y + dims.z) / 4
            axle_len = dims.x * 1.5
        elif dims.y < dims.x and dims.y < dims.z:
            axle_axis = 'Y'
            radius = (dims.x + dims.z) / 4
            axle_len = dims.y * 1.5
        else:
            axle_axis = 'Z'
            radius = (dims.x + dims.y) / 4
            axle_len = dims.z * 1.5

        if axle_diameter is None:
            axle_diameter_m = radius * 0.4 # 40% of radius as default
        else:
            axle_diameter_m = float(axle_diameter) / 1000.0 # Convert mm to m

        if hole_depth is None:
            hole_depth_m = axle_len * 2
        else:
            hole_depth_m = float(hole_depth) / 1000.0
            
        clearance_m = float(clearance) / 1000.0
        
        # Create helper cylinder for the pin (joined to wheel)
        bpy.ops.mesh.primitive_cylinder_add(
            radius=axle_diameter_m / 2,
            depth=axle_len,
            location=center
        )
        pin = bpy.context.active_object
        pin.name = f"Axle_Pin_{wheel_name}"
        
        # Orient pin
        if axle_axis == 'X':
            pin.rotation_euler[1] = math.radians(90)
        elif axle_axis == 'Y':
            pin.rotation_euler[0] = math.radians(90)
            
        # Create helper cylinder for the hole (cutter for chassis)
        bpy.ops.mesh.primitive_cylinder_add(
            radius=(axle_diameter_m / 2) + clearance_m,
            depth=hole_depth_m,
            location=center
        )
        cutter = bpy.context.active_object
        cutter.name = f"Axle_Cutter_{wheel_name}"
        cutter.rotation_euler = pin.rotation_euler.copy()
        
        # Apply boolean to chassis (Hole)
        mod_hole = chassis.modifiers.new(name=f"Hole_{wheel_name}", type='BOOLEAN')
        mod_hole.object = cutter
        mod_hole.operation = 'DIFFERENCE'
        mod_hole.solver = 'EXACT'
        
        # Hide cutter
        cutter.display_type = 'WIRE'
        cutter.hide_render = True
        cutter.hide_viewport = True
        
        # Join pin to wheel or apply Union
        mod_pin = wheel.modifiers.new(name=f"Axle_Pin", type='BOOLEAN')
        mod_pin.object = pin
        mod_pin.operation = 'UNION'
        mod_pin.solver = 'EXACT'
        
        # Hide pin
        pin.display_type = 'WIRE'
        pin.hide_render = True
        pin.hide_viewport = True

        return {
            "success": True,
            "message": f"Created axle joint between '{chassis_name}' and '{wheel_name}'.",
            "axle_axis": axle_axis,
            "axle_diameter_mm": axle_diameter_m * 1000,
            "clearance_mm": clearance
        }
    except Exception as e:
        return {"error": f"Failed to create axle joint: {str(e)}"}
