"""Mechanical tools for BlenderMCP."""

import math

import bpy
import mathutils


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
        mod_pin = wheel.modifiers.new(name="Axle_Pin", type='BOOLEAN')
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


def create_hinge_joint(scene, part1_name, part2_name, location=None, axis=(0, 1, 0), diameter=3.0, clearance=0.2):
    """Create a hinge joint between two parts at a specific location."""
    try:
        if part1_name not in scene.objects or part2_name not in scene.objects:
            return {"error": "One or both parts not found."}

        p1 = scene.objects[part1_name]
        p2 = scene.objects[part2_name]

        if location is None:
            # Fallback to midpoint between bounding boxes if no location provided
            bpy.context.view_layer.update()
            loc1 = p1.matrix_world.translation
            loc2 = p2.matrix_world.translation
            location = (loc1 + loc2) / 2

        dia_m = float(diameter) / 1000.0
        clearance_m = float(clearance) / 1000.0
        axis_vec = mathutils.Vector(axis).normalized()

        # Create the Pin (Cylinder)
        bpy.ops.mesh.primitive_cylinder_add(
            radius=dia_m / 2,
            depth=dia_m * 5, # Arbitrary length for now
            location=location
        )
        pin = bpy.context.active_object
        pin.name = f"Hinge_Pin_{part1_name}_{part2_name}"
        
        # Align pin to axis
        rot_quat = mathutils.Vector((0, 0, 1)).rotation_difference(axis_vec)
        pin.rotation_mode = 'QUATERNION'
        pin.rotation_quaternion = rot_quat

        # Create Cutter for Part 1 (with clearance)
        bpy.ops.mesh.primitive_cylinder_add(
            radius=(dia_m / 2) + clearance_m,
            depth=dia_m * 5.2,
            location=location
        )
        cutter1 = bpy.context.active_object
        cutter1.name = "Hinge_Cutter_P1"
        cutter1.rotation_mode = 'QUATERNION'
        cutter1.rotation_quaternion = rot_quat

        # Apply Hole to Part 1
        mod1 = p1.modifiers.new(name="Hinge_Hole", type='BOOLEAN')
        mod1.object = cutter1
        mod1.operation = 'DIFFERENCE'
        mod1.solver = 'EXACT'
        cutter1.hide_viewport = True
        cutter1.hide_render = True

        # Apply Hole to Part 2
        cutter2 = cutter1.copy()
        cutter2.data = cutter1.data.copy()
        scene.collection.objects.link(cutter2)
        cutter2.name = "Hinge_Cutter_P2"
        
        mod2 = p2.modifiers.new(name="Hinge_Hole", type='BOOLEAN')
        mod2.object = cutter2
        mod2.operation = 'DIFFERENCE'
        mod2.solver = 'EXACT'
        cutter2.hide_viewport = True
        cutter2.hide_render = True

        return {
            "success": True,
            "message": f"Created hinge holes at {location} for '{part1_name}' and '{part2_name}'. Insert a {diameter}mm pin.",
            "pin_object": pin.name
        }
    except Exception as e:
        return {"error": f"Failed to create hinge: {str(e)}"}


def create_snap_fit(scene, female_part_name, male_part_name, location=None, width=10.0, height=15.0, thickness=2.0):
    """Create a simple cantilever snap-fit joint between two parts."""
    try:
        if female_part_name not in scene.objects or male_part_name not in scene.objects:
            return {"error": "One or both parts not found."}

        p_female = scene.objects[female_part_name]
        p_male = scene.objects[male_part_name]

        if location is None:
            bpy.context.view_layer.update()
            location = (p_female.matrix_world.translation + p_male.matrix_world.translation) / 2

        w = float(width) / 1000.0
        h = float(height) / 1000.0
        t = float(thickness) / 1000.0

        # Create the snap-fit geometry (a simple hook shape)
        # Using a mesh creation helper
        vertices = [
            (0, -w/2, 0), (t, -w/2, 0), (t, w/2, 0), (0, w/2, 0),
            (0, -w/2, h), (t, -w/2, h), (t, w/2, h), (0, w/2, h),
            (t*2, -w/2, h-t), (t*2, w/2, h-t) # Hook part
        ]
        faces = [
            (0,1,2,3), (4,5,6,7), (0,4,5,1), (1,5,6,2), (2,6,7,3), (3,7,4,0),
            (5,8,9,6), (5,6,9,8) # Simple hook tip
        ]
        
        mesh = bpy.data.meshes.new("SnapFit")
        snap_obj = bpy.data.objects.new("SnapFit_Male", mesh)
        scene.collection.objects.link(snap_obj)
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        
        snap_obj.location = location
        
        # Apply Union to male part
        mod = p_male.modifiers.new(name="SnapFit_Hook", type='BOOLEAN')
        mod.object = snap_obj
        mod.operation = 'UNION'
        mod.solver = 'EXACT'
        
        # Create cutter for female part (with clearance)
        # Offset snap_obj or create a slightly larger one
        cutter_obj = snap_obj.copy()
        cutter_obj.data = snap_obj.data.copy()
        scene.collection.objects.link(cutter_obj)
        cutter_obj.scale *= 1.1 # 10% clearance
        cutter_obj.name = "SnapFit_Cutter"
        
        mod_f = p_female.modifiers.new(name="SnapFit_Hole", type='BOOLEAN')
        mod_f.object = cutter_obj
        mod_f.operation = 'DIFFERENCE'
        mod_f.solver = 'EXACT'

        snap_obj.hide_viewport = True
        cutter_obj.hide_viewport = True

        return {
            "success": True,
            "message": f"Created cantilever snap-fit between '{male_part_name}' and '{female_part_name}'.",
            "male_hook": snap_obj.name
        }
    except Exception as e:
        return {"error": f"Failed to create snap-fit: {str(e)}"}


def create_ball_joint(scene, socket_part_name, ball_part_name, location=None, diameter=10.0, clearance=0.2):
    """Create a ball-and-socket joint between two parts."""
    try:
        if socket_part_name not in scene.objects or ball_part_name not in scene.objects:
            return {"error": "One or both parts not found."}

        p_socket = scene.objects[socket_part_name]
        p_ball = scene.objects[ball_part_name]

        if location is None:
            bpy.context.view_layer.update()
            location = (p_socket.matrix_world.translation + p_ball.matrix_world.translation) / 2

        dia_m = float(diameter) / 1000.0
        clearance_m = float(clearance) / 1000.0

        # Create the Ball
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=dia_m / 2,
            location=location
        )
        ball_obj = bpy.context.active_object
        ball_obj.name = f"Ball_{ball_part_name}"
        
        # Add Ball to ball_part
        mod_b = p_ball.modifiers.new(name="Ball_Joint", type='BOOLEAN')
        mod_b.object = ball_obj
        mod_b.operation = 'UNION'
        mod_b.solver = 'EXACT'

        # Create Socket Cutter (with clearance)
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=(dia_m / 2) + clearance_m,
            location=location
        )
        socket_cutter = bpy.context.active_object
        socket_cutter.name = "Socket_Cutter"
        
        # Apply Difference to socket_part
        mod_s = p_socket.modifiers.new(name="Socket_Joint", type='BOOLEAN')
        mod_s.object = socket_cutter
        mod_s.operation = 'DIFFERENCE'
        mod_s.solver = 'EXACT'

        ball_obj.hide_viewport = True
        socket_cutter.hide_viewport = True

        return {
            "success": True,
            "message": f"Created ball joint between '{ball_part_name}' and '{socket_part_name}'. Ball diameter: {diameter}mm.",
            "ball_object": ball_obj.name
        }
    except Exception as e:
        return {"error": f"Failed to create ball joint: {str(e)}"}


def create_screw_hole(scene, part1_name, part2_name, location=None, axis=(0,0,1), screw_type="M3", countersink=True):
    """Create aligned screw holes for standard metric screws."""
    try:
        # Standard dimensions in mm (Diameter, Head Diameter, Head Depth)
        SCREW_DATA = {
            "M2": (2.2, 4.0, 1.5),
            "M2.5": (2.7, 5.0, 1.8),
            "M3": (3.3, 6.0, 2.5),
            "M4": (4.3, 8.0, 3.5),
            "M5": (5.3, 10.0, 4.5),
        }
        
        if screw_type not in SCREW_DATA:
            return {"error": f"Unsupported screw type '{screw_type}'. Use M2, M3, M4, or M5."}
            
        dia, head_dia, head_depth = [v / 1000.0 for v in SCREW_DATA[screw_type]]
        
        if part1_name not in scene.objects:
            return {"error": f"Part 1 '{part1_name}' not found."}
            
        p1 = scene.objects[part1_name]
        
        if location is None:
            location = p1.matrix_world.translation

        axis_vec = mathutils.Vector(axis).normalized()
        rot_quat = mathutils.Vector((0, 0, 1)).rotation_difference(axis_vec)

        # Create Cutter for Screw Shaft
        bpy.ops.mesh.primitive_cylinder_add(radius=dia/2, depth=dia*20, location=location)
        shaft_cutter = bpy.context.active_object
        shaft_cutter.name = f"Screw_Shaft_{screw_type}"
        shaft_cutter.rotation_mode = 'QUATERNION'
        shaft_cutter.rotation_quaternion = rot_quat
        shaft_cutter.display_type = 'WIRE'

        # Apply to Part 1
        mod1 = p1.modifiers.new(name=f"Screw_{screw_type}", type='BOOLEAN')
        mod1.object = shaft_cutter
        mod1.operation = 'DIFFERENCE'
        mod1.solver = 'EXACT'

        # Optional Countersink (Head Hole)
        if countersink:
            bpy.ops.mesh.primitive_cylinder_add(radius=head_dia/2, depth=head_depth * 2, location=location)
            head_cutter = bpy.context.active_object
            head_cutter.name = f"Screw_Head_{screw_type}"
            head_cutter.rotation_mode = 'QUATERNION'
            head_cutter.rotation_quaternion = rot_quat
            head_cutter.display_type = 'WIRE'
            
            # Move head cutter slightly along axis so it cuts the surface
            head_cutter.location += axis_vec * head_depth
            
            mod_h = p1.modifiers.new(name=f"Countersink_{screw_type}", type='BOOLEAN')
            mod_h.object = head_cutter
            mod_h.operation = 'DIFFERENCE'
            mod_h.solver = 'EXACT'
            head_cutter.hide_viewport = True

        # Apply shaft cutter to Part 2 if provided
        if part2_name and part2_name in scene.objects:
            p2 = scene.objects[part2_name]
            mod2 = p2.modifiers.new(name=f"Screw_Hole_{screw_type}", type='BOOLEAN')
            mod2.object = shaft_cutter
            mod2.operation = 'DIFFERENCE'
            mod2.solver = 'EXACT'

        shaft_cutter.hide_viewport = True

        return {
            "success": True,
            "message": f"Created {screw_type} screw holes. Countersink: {countersink}.",
            "cutters": [shaft_cutter.name]
        }
    except Exception as e:
        return {"error": f"Failed to create screw hole: {str(e)}"}
