"""3D Printing preparation tools for BlenderMCP."""

import bpy
import os


def set_exact_dimensions(scene, object_name, size_x=None, size_y=None, size_z=None):
    """Set the exact dimensions of an object in metric units (meters by default in Blender).
    If only some axes are provided, the object is scaled proportionally.
    Pass dimensions as floats.
    """
    try:
        if object_name not in scene.objects:
            return {"error": f"Object '{object_name}' not found."}
            
        obj = scene.objects[object_name]
        
        # Ensure object scaling is updated
        bpy.context.view_layer.update()
        current_dims = obj.dimensions.copy()
        
        if current_dims.x == 0 or current_dims.y == 0 or current_dims.z == 0:
            return {"error": f"Object '{object_name}' has zero dimension on at least one axis, cannot scale proportionately."}

        target_x = float(size_x) if size_x is not None else None
        target_y = float(size_y) if size_y is not None else None
        target_z = float(size_z) if size_z is not None else None

        scale_factors = []
        if target_x: scale_factors.append(target_x / current_dims.x)
        if target_y: scale_factors.append(target_y / current_dims.y)
        if target_z: scale_factors.append(target_z / current_dims.z)
        
        if not scale_factors:
            return {"error": "No new dimensions provided."}
            
        # Get base proportional scale
        base_scale = scale_factors[0]

        # Calculate final scale
        new_scale = obj.scale.copy()
        new_scale.x *= (target_x / current_dims.x) if target_x else base_scale
        new_scale.y *= (target_y / current_dims.y) if target_y else base_scale
        new_scale.z *= (target_z / current_dims.z) if target_z else base_scale

        obj.scale = new_scale
        bpy.context.view_layer.update()
        
        # Apply scale so dimensions become standard for 3D printing
        # Equivalent to Ctrl+A -> Scale
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        # Apply scale directly via matrix manipulation to avoid context context errors in headless run
        for i in range(3):
            obj.scale[i] = 1.0
            for v in obj.data.vertices:
                v.co[i] *= new_scale[i]

        bpy.context.view_layer.update()
        final_dims = obj.dimensions
        
        return {
            "success": True,
            "message": f"Successfully resized '{object_name}'. Scale applied.",
            "final_dimensions": {"x": final_dims.x, "y": final_dims.y, "z": final_dims.z}
        }
    except Exception as e:
        return {"error": f"Failed to set dimensions: {str(e)}"}


def apply_print_thickness(scene, object_name, thickness_mm, offset=0.0):
    """Apply generic Solidify modifier to create printer-friendly shells.
    thickness_mm is standard millimeters. Offset determines if thickness goes inward (-1), outward (1) or center (0).
    """
    try:
        if object_name not in scene.objects:
            return {"error": f"Object '{object_name}' not found."}
            
        obj = scene.objects[object_name]
        
        if obj.type != 'MESH':
            return {"error": f"Object '{object_name}' is not a MESH."}

        # Millimeters to meters conversion (Blender's default base unit)
        thickness_meters = float(thickness_mm) / 1000.0

        mod_name = "3DPrint_Solidify"
        mod = obj.modifiers.get(mod_name)
        if not mod:
            mod = obj.modifiers.new(name=mod_name, type='SOLIDIFY')

        mod.thickness = thickness_meters
        mod.offset = float(offset)
        mod.use_even_offset = True  # Better for corners in mechanical/hard-surface models
        mod.use_quality_normals = True

        return {
            "success": True,
            "message": f"Applied {thickness_mm}mm thickness to '{object_name}'.",
            "modifier_name": mod.name
        }
    except Exception as e:
        return {"error": f"Failed to apply thickness: {str(e)}"}


def apply_boolean_operation(scene, target_name, tool_name, operation="DIFFERENCE"):
    """Use a tool object to cut (DIFFERENCE), union (UNION), or intersect (INTERSECT) the target object."""
    try:
        if target_name not in scene.objects:
            return {"error": f"Target object '{target_name}' not found."}
        if tool_name not in scene.objects:
            return {"error": f"Tool object '{tool_name}' not found."}
            
        target_obj = scene.objects[target_name]
        tool_obj = scene.objects[tool_name]
        
        if operation.upper() not in ["INTERSECT", "UNION", "DIFFERENCE"]:
             return {"error": f"Invalid operation '{operation}'. Use INTERSECT, UNION, or DIFFERENCE."}

        mod_name = f"Bool_{operation.capitalize()}_{tool_name}"
        mod = target_obj.modifiers.new(name=mod_name, type='BOOLEAN')
        
        mod.operation = operation.upper()
        mod.object = tool_obj
        mod.solver = 'EXACT'  # Usually safer for precise CAD/Hard surface models
        
        # Hide the tool object from viewport & render to observe the cut
        tool_obj.display_type = 'WIRE'
        tool_obj.hide_render = True

        return {
            "success": True,
            "message": f"Applied {operation} boolean on '{target_name}' using '{tool_name}'. Tool is hidden in wireframe mode.",
            "modifier_name": mod.name
        }
    except Exception as e:
        return {"error": f"Failed to apply boolean: {str(e)}"}


def export_for_printing(scene, object_names=None, filepath=None):
    """Export specified objects (or all selected) directly to an STL file."""
    try:
        if not filepath:
            filepath = os.path.join(os.path.expanduser("~"), "blender_mcp_export.stl")
            
        # Ensure correct extension
        if not filepath.lower().endswith(".stl"):
            filepath += ".stl"
            
        # Select objects to export
        bpy.ops.object.select_all(action='DESELECT')
        export_count = 0
        
        if object_names:
            if isinstance(object_names, str):
                object_names = [object_names]
            for name in object_names:
                if name in scene.objects:
                    scene.objects[name].select_set(True)
                    export_count += 1
        else:
            # If no objects specified, export all meshes
            for obj in scene.objects:
                if obj.type == 'MESH':
                    obj.select_set(True)
                    export_count += 1

        if export_count == 0:
             return {"error": "No valid mesh objects to export."}

        # Export operator (STL is built-in)
        # using use_selection=True to only export what we selected
        # ASCII=False (binary is smaller)
        bpy.ops.export_mesh.stl(
            filepath=filepath,
            use_selection=True,
            use_mesh_modifiers=True,  # Apply solidify, booleans, etc.
            ascii=False,
            # Blender uses Z-up, Y-forward for generic 3D space, which matches most slicers (Cura/PrusaSlicer) natively when exported directly
            global_scale=1.0  
        )

        return {
            "success": True,
            "message": f"Exported {export_count} objects to {filepath}",
            "filepath": filepath,
            "objects_exported": export_count
        }

    except Exception as e:
        return {"error": f"Failed to export for printing: {str(e)}"}
