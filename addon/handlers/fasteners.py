"""Procedural Standard Fasteners Library for BlenderMCP."""

import math

import bpy
import mathutils

from ..core.router import mcp_command


@mcp_command(name="generate_fastener", read_only=False)
def generate_fastener(
    scene,
    type="SCREW",
    size="M3",
    length=10.0,
    head_type="SOCKET",
    location=(0, 0, 0),
    axis=(0, 0, 1),
):
    """Generate a standard metric fastener (Screw, Nut, Washer, Bearing) procedurally."""
    try:
        # Standard dimensions in mm
        # Screws: (shaft_dia, head_dia, head_depth)
        SCREW_DIM = {
            "M2": {"dia": 2.0, "HEX": (4.0, 1.4), "SOCKET": (3.8, 2.0), "BUTTON": (3.5, 1.2)},
            "M2.5": {"dia": 2.5, "HEX": (5.0, 1.7), "SOCKET": (4.5, 2.5), "BUTTON": (4.7, 1.5)},
            "M3": {"dia": 3.0, "HEX": (5.5, 2.0), "SOCKET": (5.5, 3.0), "BUTTON": (5.7, 1.65)},
            "M4": {"dia": 4.0, "HEX": (7.0, 2.8), "SOCKET": (7.0, 4.0), "BUTTON": (7.6, 2.2)},
            "M5": {"dia": 5.0, "HEX": (8.0, 3.5), "SOCKET": (8.5, 5.0), "BUTTON": (9.5, 2.75)},
            "M6": {"dia": 6.0, "HEX": (10.0, 4.0), "SOCKET": (10.0, 6.0), "BUTTON": (10.5, 3.3)},
            "M8": {"dia": 8.0, "HEX": (13.0, 5.3), "SOCKET": (13.0, 8.0), "BUTTON": (14.0, 4.4)},
        }

        # Nuts: (width_flats, thickness)
        NUT_DIM = {
            "M2": (4.0, 1.6),
            "M2.5": (5.0, 2.0),
            "M3": (5.5, 2.4),
            "M4": (7.0, 3.2),
            "M5": (8.0, 4.7),
            "M6": (10.0, 5.2),
            "M8": (13.0, 6.8),
        }

        # Washers: (ID, OD, thickness)
        WASHER_DIM = {
            "M2": (2.2, 5.0, 0.3),
            "M2.5": (2.7, 6.0, 0.5),
            "M3": (3.2, 7.0, 0.5),
            "M4": (4.3, 9.0, 0.8),
            "M5": (5.3, 10.0, 1.0),
            "M6": (6.4, 12.0, 1.6),
            "M8": (8.4, 16.0, 1.6),
        }

        # Bearings: (ID, OD, width)
        BEARING_DIM = {
            "608": (8.0, 22.0, 7.0),
            "623": (3.0, 10.0, 4.0),
            "625": (5.0, 16.0, 5.0),
            "688": (8.0, 16.0, 5.0),
        }

        axis_vec = mathutils.Vector(axis).normalized()
        rot_quat = mathutils.Vector((0, 0, 1)).rotation_difference(axis_vec)
        loc_vec = mathutils.Vector(location)

        created_objects = []

        if type.upper() == "SCREW":
            if size not in SCREW_DIM:
                return {"error": f"Size '{size}' not supported for Screw."}
            dim = SCREW_DIM[size]
            shaft_dia = dim["dia"] / 1000.0
            length_m = float(length) / 1000.0

            h_type = head_type.upper() if head_type.upper() in dim else "SOCKET"
            head_dia, head_depth = [v / 1000.0 for v in dim[h_type]]

            # 1. Create Shaft Cylinder
            # Offset shaft center along axis so head is at location
            shaft_loc = loc_vec - axis_vec * (length_m / 2)
            bpy.ops.mesh.primitive_cylinder_add(
                radius=shaft_dia / 2, depth=length_m, location=shaft_loc
            )
            shaft = bpy.context.active_object
            shaft.name = f"Screw_Shaft_{size}x{int(length)}"
            shaft.rotation_mode = "QUATERNION"
            shaft.rotation_quaternion = rot_quat
            created_objects.append(shaft)

            # 2. Create Head Cylinder
            head_loc = loc_vec + axis_vec * (head_depth / 2)
            if h_type == "HEX":
                bpy.ops.mesh.primitive_cylinder_add(
                    vertices=6,
                    radius=(head_dia / math.sqrt(3)),
                    depth=head_depth,
                    location=head_loc,
                )
            else:
                bpy.ops.mesh.primitive_cylinder_add(
                    radius=head_dia / 2, depth=head_depth, location=head_loc
                )
            head = bpy.context.active_object
            head.name = f"Screw_Head_{size}_{h_type}"
            head.rotation_mode = "QUATERNION"
            head.rotation_quaternion = rot_quat
            created_objects.append(head)

            # Join Head and Shaft
            bpy.ops.object.select_all(action="DESELECT")
            shaft.select_set(True)
            head.select_set(True)
            scene.view_layer.objects.active = shaft
            bpy.ops.object.join()
            shaft.name = f"Fastener_Screw_{size}x{int(length)}"

            return {
                "success": True,
                "message": f"Generated {size}x{int(length)}mm screw ({head_type}) at {location}.",
                "object_name": shaft.name,
            }

        elif type.upper() == "NUT":
            if size not in NUT_DIM:
                return {"error": f"Size '{size}' not supported for Nut."}
            width_flats, thickness = [v / 1000.0 for v in NUT_DIM[size]]
            inner_dia = SCREW_DIM[size]["dia"] / 1000.0
            radius_circ = width_flats / math.sqrt(3)

            # Create Hex outer body
            bpy.ops.mesh.primitive_cylinder_add(
                vertices=6, radius=radius_circ, depth=thickness, location=location
            )
            nut = bpy.context.active_object
            nut.name = f"Fastener_Nut_{size}"
            nut.rotation_mode = "QUATERNION"
            nut.rotation_quaternion = rot_quat

            # Create inner cut hole
            bpy.ops.mesh.primitive_cylinder_add(
                radius=inner_dia / 2, depth=thickness * 1.5, location=location
            )
            hole = bpy.context.active_object
            hole.name = "Nut_Hole_Temp"
            hole.rotation_mode = "QUATERNION"
            hole.rotation_quaternion = rot_quat
            hole.hide_viewport = True

            # Boolean cut
            mod = nut.modifiers.new(name="Nut_Thread_Hole", type="BOOLEAN")
            mod.object = hole
            mod.operation = "DIFFERENCE"
            mod.solver = "EXACT"

            return {
                "success": True,
                "message": f"Generated {size} ISO Hex Nut at {location}.",
                "object_name": nut.name,
            }

        elif type.upper() == "WASHER":
            if size not in WASHER_DIM:
                return {"error": f"Size '{size}' not supported for Washer."}
            inner_dia, outer_dia, thickness = [v / 1000.0 for v in WASHER_DIM[size]]

            # Create Washer outer cylinder
            bpy.ops.mesh.primitive_cylinder_add(
                radius=outer_dia / 2, depth=thickness, location=location
            )
            washer = bpy.context.active_object
            washer.name = f"Fastener_Washer_{size}"
            washer.rotation_mode = "QUATERNION"
            washer.rotation_quaternion = rot_quat

            # Create inner cut hole
            bpy.ops.mesh.primitive_cylinder_add(
                radius=inner_dia / 2, depth=thickness * 1.5, location=location
            )
            hole = bpy.context.active_object
            hole.name = "Washer_Hole_Temp"
            hole.rotation_mode = "QUATERNION"
            hole.rotation_quaternion = rot_quat
            hole.hide_viewport = True

            # Boolean cut
            mod = washer.modifiers.new(name="Washer_Hole", type="BOOLEAN")
            mod.object = hole
            mod.operation = "DIFFERENCE"
            mod.solver = "EXACT"

            return {
                "success": True,
                "message": f"Generated {size} Washer at {location}.",
                "object_name": washer.name,
            }

        elif type.upper() == "BEARING":
            if size not in BEARING_DIM:
                return {"error": f"Bearing type '{size}' not supported. Use 608, 623, 625, 688."}
            inner_dia, outer_dia, width = [v / 1000.0 for v in BEARING_DIM[size]]

            # Outer ring
            bpy.ops.mesh.primitive_cylinder_add(
                radius=outer_dia / 2, depth=width, location=location
            )
            outer_ring = bpy.context.active_object
            outer_ring.name = f"Bearing_{size}_Outer"
            outer_ring.rotation_mode = "QUATERNION"
            outer_ring.rotation_quaternion = rot_quat

            # Inner hole cutter
            bpy.ops.mesh.primitive_cylinder_add(
                radius=inner_dia / 2, depth=width * 1.5, location=location
            )
            inner_hole = bpy.context.active_object
            inner_hole.name = "Bearing_Hole_Temp"
            inner_hole.rotation_mode = "QUATERNION"
            inner_hole.rotation_quaternion = rot_quat
            inner_hole.hide_viewport = True

            # Middle shield gap cutter
            inner_dia * 0.6 + outer_dia * 0.4
            inner_dia * 0.4 + outer_dia * 0.6

            # Subtraction for hole
            mod_h = outer_ring.modifiers.new(name="Hole", type="BOOLEAN")
            mod_h.object = inner_hole
            mod_h.operation = "DIFFERENCE"
            mod_h.solver = "EXACT"

            return {
                "success": True,
                "message": f"Generated Ball Bearing {size} at {location}.",
                "object_name": outer_ring.name,
            }

        else:
            return {"error": f"Unknown fastener type: {type}."}

    except Exception as e:
        return {"error": f"Failed to generate fastener: {str(e)}"}
