"""Animation tools for BlenderMCP."""
from ..core.router import mcp_command

import bpy
import math

@mcp_command(name="animate_rotation", read_only=False)
def animate_rotation(scene, object_name, axis='Z', degrees=360.0, start_frame=1, end_frame=250):
    """Animate continuous rotation of an object along a specific axis."""
    try:
        obj = scene.objects.get(object_name)
        if not obj:
            return {"error": f"Object '{object_name}' not found."}
            
        axis = axis.upper()
        if axis not in ['X', 'Y', 'Z']:
            return {"error": "Axis must be X, Y, or Z"}
            
        axis_index = {'X': 0, 'Y': 1, 'Z': 2}[axis]
        
        # Clear existing animation on this object if any
        if obj.animation_data and obj.animation_data.action:
            obj.animation_data_clear()
            
        # Ensure rotation mode is Euler
        obj.rotation_mode = 'XYZ'
        
        # Insert keyframe at start
        obj.rotation_euler[axis_index] = 0.0
        obj.keyframe_insert(data_path="rotation_euler", index=axis_index, frame=start_frame)
        
        # Insert keyframe at end
        obj.rotation_euler[axis_index] = math.radians(float(degrees))
        obj.keyframe_insert(data_path="rotation_euler", index=axis_index, frame=end_frame)
        
        # Set interpolation to linear for continuous smooth motion
        if obj.animation_data and obj.animation_data.action:
            for fcurve in obj.animation_data.action.fcurves:
                for keyframe in fcurve.keyframe_points:
                    keyframe.interpolation = 'LINEAR'
                    
        # Update scene frame range
        scene.frame_start = int(start_frame)
        scene.frame_end = int(end_frame)
        
        return {
            "success": True,
            "message": f"Animated '{object_name}' rotating {degrees} degrees on {axis} axis from frame {start_frame} to {end_frame}."
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": f"Failed to animate rotation: {str(e)}"}


@mcp_command(name="create_turntable_animation", read_only=False)
def create_turntable_animation(scene, target_object_name, frames=250, distance=10.0, height=3.0):
    """Create a camera orbiting around a specific object for a turntable animation."""
    try:
        target = scene.objects.get(target_object_name)
        if not target:
            return {"error": f"Target object '{target_object_name}' not found."}
            
        # Create an Empty at the target's location to act as the pivot
        bpy.ops.object.empty_add(type='PLAIN_AXES', align='WORLD', location=target.location)
        pivot = bpy.context.active_object
        pivot.name = f"Turntable_Pivot_{target.name}"
        
        # Create camera
        cam_data = bpy.data.cameras.new(name=f"Turntable_Cam_{target.name}")
        cam_obj = bpy.data.objects.new(f"Turntable_Cam_{target.name}", cam_data)
        scene.collection.objects.link(cam_obj)
        scene.camera = cam_obj
        
        # Parent camera to pivot
        cam_obj.parent = pivot
        
        # Move camera away and up
        cam_obj.location = (0, -float(distance), float(height))
        
        # Make camera look at pivot (using constraint)
        constraint = cam_obj.constraints.new(type='TRACK_TO')
        constraint.target = pivot
        constraint.track_axis = 'TRACK_NEGATIVE_Z'
        constraint.up_axis = 'UP_Y'
        
        # Animate the pivot rotating 360 degrees
        pivot.rotation_mode = 'XYZ'
        pivot.rotation_euler[2] = 0.0
        pivot.keyframe_insert(data_path="rotation_euler", index=2, frame=1)
        
        pivot.rotation_euler[2] = math.radians(360)
        pivot.keyframe_insert(data_path="rotation_euler", index=2, frame=int(frames))
        
        # Set interpolation to linear
        if pivot.animation_data and pivot.animation_data.action:
            for fcurve in pivot.animation_data.action.fcurves:
                for keyframe in fcurve.keyframe_points:
                    keyframe.interpolation = 'LINEAR'
                    
        scene.frame_start = 1
        scene.frame_end = int(frames)
        
        return {
            "success": True,
            "message": f"Turntable camera created around '{target.name}' lasting {frames} frames."
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": f"Failed to create turntable: {str(e)}"}
