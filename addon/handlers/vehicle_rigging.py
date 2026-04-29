"""Vehicle rigging tools for BlenderMCP."""
from ..core.router import mcp_command


import bpy


@mcp_command(name="setup_simple_vehicle_rig", read_only=False)
def setup_simple_vehicle_rig(scene, chassis_name, wheel_names):
    """Setup a basic rig for a vehicle with steering and driving controls."""
    try:
        if chassis_name not in scene.objects:
            return {"error": f"Chassis '{chassis_name}' not found."}

        chassis = scene.objects[chassis_name]
        wheels = [scene.objects[name] for name in wheel_names if name in scene.objects]

        if not wheels:
            return {"error": "No valid wheels provided for rigging."}

        # 1. Create a Master Control (Root Empty)
        bpy.ops.object.empty_add(type='CUBE', location=chassis.location)
        root = bpy.context.active_object
        root.name = f"RIG_{chassis_name}_Root"
        root.scale = (2, 2, 2)

        # 2. Parent Chassis to Root
        chassis.parent = root
        chassis.matrix_parent_inverse = root.matrix_world.inverted()

        # 3. Setup Wheels
        # Identify front and back wheels by local position
        wheel_data = []
        for wheel in wheels:
            local_pos = chassis.matrix_world.inverted() @ wheel.location
            is_front = local_pos.y > 0 # Simple heuristic: Y+ is forward
            wheel_data.append({'obj': wheel, 'is_front': is_front, 'local_pos': local_pos})

        # Create Steer and Drive properties on the Root
        root["Steer"] = 0.0
        root["Drive"] = 0.0

        # Add UI for properties
        # (Usually done via panel, but we can setup drivers here)

        for data in wheel_data:
            wheel = data['obj']

            # Create a pivot for steering if front wheel
            if data['is_front']:
                bpy.ops.object.empty_add(type='PLAIN_AXES', location=wheel.location)
                pivot = bpy.context.active_object
                pivot.name = f"Pivot_{wheel.name}"
                pivot.parent = root
                pivot.matrix_parent_inverse = root.matrix_world.inverted()

                wheel.parent = pivot
                wheel.matrix_parent_inverse = pivot.matrix_world.inverted()

                # Add Steering Driver
                driver = pivot.driver_add("rotation_euler", 2) # Z axis
                var = driver.driver.variables.new()
                var.name = "steer"
                var.targets[0].id = root
                var.targets[0].data_path = '["Steer"]'
                driver.driver.expression = "steer * 0.5" # 0.5 rad (~30 deg) max
            else:
                wheel.parent = root
                wheel.matrix_parent_inverse = root.matrix_world.inverted()

            # Add Drive Driver (Rotation around axle)
            # Find axle axis (heuristic from printing3d handler)
            dims = wheel.dimensions
            if dims.x < dims.y and dims.x < dims.z:
                axis_idx = 0
            elif dims.y < dims.x and dims.y < dims.z:
                axis_idx = 1
            else:
                axis_idx = 2

            driver = wheel.driver_add("rotation_euler", axis_idx)
            var = driver.driver.variables.new()
            var.name = "drive"
            var.targets[0].id = root
            var.targets[0].data_path = '["Drive"]'
            driver.driver.expression = "drive * 10" # arbitrary multiplier

        return {
            "success": True,
            "message": f"Setup vehicle rig for '{chassis_name}' with {len(wheels)} wheels.",
            "root_control": root.name,
            "controls": ["Steer", "Drive"]
        }
    except Exception as e:
        return {"error": f"Failed to setup vehicle rig: {str(e)}"}
