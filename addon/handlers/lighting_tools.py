"""Lighting tools for BlenderMCP."""
from ..core.router import mcp_command

import bpy
import math

@mcp_command(name="setup_three_point_lighting", read_only=False)
def setup_three_point_lighting(scene, target_object_name=None, energy_multiplier=1.0, distance=5.0):
    """Create a professional 3-point lighting setup around a target object."""
    try:
        # Determine target center
        target = None
        center = (0, 0, 0)
        
        if target_object_name:
            target = scene.objects.get(target_object_name)
            if target:
                center = target.location
            else:
                return {"error": f"Target object '{target_object_name}' not found."}
        else:
            # If no target, try active object or origin
            if context := bpy.context:
                if context.active_object:
                    target = context.active_object
                    center = target.location
                    
        dist = float(distance)
        mult = float(energy_multiplier)
        
        # Helper to create and track light
        def create_light(name, type, location, energy, color, track_to=None):
            light_data = bpy.data.lights.new(name=name, type=type)
            light_data.energy = energy
            light_data.color = color
            
            # Larger size for softer shadows
            if type == 'AREA':
                light_data.size = dist * 0.5
            
            obj = bpy.data.objects.new(name=name, object_data=light_data)
            scene.collection.objects.link(obj)
            obj.location = location
            
            if track_to:
                constraint = obj.constraints.new(type='TRACK_TO')
                constraint.target = track_to
                constraint.track_axis = 'TRACK_NEGATIVE_Z'
                constraint.up_axis = 'UP_Y'
                
            return obj
            
        # Optional: create a tracking empty if we don't have a specific target
        track_target = target
        if not track_target:
            bpy.ops.object.empty_add(type='PLAIN_AXES', location=center)
            track_target = bpy.context.active_object
            track_target.name = "Lighting_Target"

        # 1. Key Light (Main light, strongest, warm, 45 deg front-right, high up)
        key_loc = (
            center[0] + dist, 
            center[1] - dist, 
            center[2] + dist
        )
        # Area light for soft shadows, 1000W equivalent
        key_light = create_light("Light_Key", 'AREA', key_loc, 1000.0 * mult, (1.0, 0.95, 0.9), track_target)
        
        # 2. Fill Light (Softer, cooler, 45 deg front-left, lower)
        fill_loc = (
            center[0] - dist, 
            center[1] - (dist * 0.5), 
            center[2] + (dist * 0.5)
        )
        # 300W equivalent
        fill_light = create_light("Light_Fill", 'AREA', fill_loc, 300.0 * mult, (0.9, 0.95, 1.0), track_target)
        
        # 3. Rim Light (Backlight, separates from background, sharp, opposite to key)
        rim_loc = (
            center[0] - (dist * 0.5), 
            center[1] + dist, 
            center[2] + (dist * 0.8)
        )
        # 800W equivalent, pure white
        rim_light = create_light("Light_Rim", 'SPOT', rim_loc, 800.0 * mult, (1.0, 1.0, 1.0), track_target)
        # Set spot settings
        rim_light.data.spot_size = math.radians(45)
        rim_light.data.spot_blend = 0.5

        return {
            "success": True,
            "message": f"3-Point lighting setup created around {target.name if target else 'origin'} with distance {dist}."
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": f"Failed to setup lighting: {str(e)}"}
