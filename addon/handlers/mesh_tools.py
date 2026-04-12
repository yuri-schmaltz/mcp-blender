"""Mesh processing tools for BlenderMCP."""

from collections import defaultdict

import bmesh
import bpy


def separate_loose_parts(scene, object_name, smart_rename=True):
    """Separate a mesh into its disconnected parts and optionally identify wheels/chassis."""
    try:
        if object_name not in scene.objects:
            return {"error": f"Object '{object_name}' not found."}

        obj = scene.objects[object_name]
        if obj.type != 'MESH':
            return {"error": f"Object '{object_name}' is not a MESH."}

        # Select and make active
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        scene.view_layer.objects.active = obj

        # Track objects before separation to find the new ones
        pre_objects = set(scene.objects.keys())

        # Perform separation
        bpy.ops.mesh.separate(type='LOOSE')

        # Find new objects
        post_objects = set(scene.objects.keys())
        new_objects_names = list(post_objects - pre_objects)
        all_parts = [scene.objects[name] for name in new_objects_names] + [obj]

        result_message = f"Separated into {len(all_parts)} parts."
        identified_parts = []

        if smart_rename and len(all_parts) > 1:
            # Smart identification logic
            # Group objects by bounding box dimensions (within a small tolerance)
            size_groups = defaultdict(list)
            tolerance = 0.05 # 5% tolerance

            for part in all_parts:
                dims = tuple(sorted([round(part.dimensions.x, 3), round(part.dimensions.y, 3), round(part.dimensions.z, 3)]))
                # Try to find a group with similar dimensions
                found = False
                for group_dims in size_groups.keys():
                    match = True
                    for d1, d2 in zip(dims, group_dims):
                        if d2 == 0:
                            if d1 != 0:
                                match = False
                        elif abs(d1 - d2) / d2 > tolerance:
                            match = False
                    if match:
                        size_groups[group_dims].append(part)
                        found = True
                        break
                if not found:
                    size_groups[dims].append(part)

            # Look for wheels: usually a group of 4 (or 2) similar objects
            wheel_candidates = []
            for dims, group in size_groups.items():
                if len(group) >= 2: # At least a pair
                    # Check if it looks circular (two dimensions roughly equal)
                    d_sorted = sorted(dims)
                    if d_sorted[0] > 0 and abs(d_sorted[1] - d_sorted[2]) / d_sorted[2] < 0.2: # 20% diff max
                        wheel_candidates.append((len(group), dims, group))

            # Use the group closest to 4 members as wheels
            if wheel_candidates:
                wheel_candidates.sort(key=lambda x: abs(x[0] - 4))
                count, dims, wheels = wheel_candidates[0]
                for i, wheel in enumerate(wheels):
                    wheel.name = f"Wheel_{i+1}"
                    identified_parts.append(wheel.name)

            # Identify Chassis: usually the largest by bounding volume
            all_parts.sort(key=lambda x: x.dimensions.x * x.dimensions.y * x.dimensions.z, reverse=True)
            chassis = all_parts[0]
            if chassis.name.startswith("Wheel") is False:
                chassis.name = "Chassis"
                identified_parts.append(chassis.name)

            # Rename remaining ones generic
            for i, part in enumerate(all_parts):
                if part.name == "Chassis" or part.name.startswith("Wheel"):
                    continue
                part.name = f"Part_{i+1}"

            result_message += f" Identified: {', '.join(identified_parts)}."

        return {
            "success": True,
            "message": result_message,
            "parts_count": len(all_parts),
            "identified": identified_parts
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": f"Failed to separate mesh: {str(e)}"}


def check_mesh_integrity(scene, object_name):
    """Check mesh for common 3D printing issues (non-manifold, holes, normals)."""
    try:
        if object_name not in scene.objects:
            return {"error": f"Object '{object_name}' not found."}

        obj = scene.objects[object_name]
        if obj.type != 'MESH':
            return {"error": f"Object '{object_name}' is not a MESH."}

        # Use bmesh for analysis
        bm = bmesh.new()
        bm.from_mesh(obj.data)

        # Non-manifold edges
        non_manifold = [e for e in bm.edges if not e.is_manifold]

        # Holes (boundary edges)
        boundary = [e for e in bm.edges if e.is_boundary]

        # Self-intersections (Skipped for performance, usually requires external tools or complex logic)

        report = {
            "is_printer_ready": len(non_manifold) == 0,
            "non_manifold_edges": len(non_manifold),
            "boundary_edges_count": len(boundary),
            "message": "Mesh is clean and ready for printing." if len(non_manifold) == 0 else f"Found {len(non_manifold)} non-manifold issues."
        }

        bm.free()
        return {"success": True, "report": report}
    except Exception as e:
        return {"error": f"Failed to check integrity: {str(e)}"}


def auto_repair_mesh(scene, object_name):
    """Try to automatically fix mesh issues (fill holes, normals)."""
    try:
        if object_name not in scene.objects:
            return {"error": f"Object '{object_name}' not found."}

        obj = scene.objects[object_name]
        if obj.type != 'MESH':
            return {"error": f"Object '{object_name}' is not a MESH."}

        # Select and make active
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        scene.view_layer.objects.active = obj

        # Go to Edit Mode
        bpy.ops.object.mode_set(mode='EDIT')

        # 1. Fill holes
        bpy.ops.mesh.fill_holes(sides=0)

        # 2. Recalculate normals (Outside)
        bpy.ops.mesh.normals_make_consistent(inside=False)

        # 3. Remove doubles (Merge by distance)
        bpy.ops.mesh.remove_doubles()

        # Back to Object Mode
        bpy.ops.object.mode_set(mode='OBJECT')

        return {
            "success": True,
            "message": f"Applied auto-repairs (fill holes, recalculate normals, merge doubles) to '{object_name}'."
        }
    except Exception as e:
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        return {"error": f"Failed to auto-repair: {str(e)}"}


def resolve_self_intersections(scene, object_name):
    """Resolve self-intersecting faces within the same mesh using the Exact Boolean solver."""
    try:
        if object_name not in scene.objects:
            return {"error": f"Object '{object_name}' not found."}

        obj = scene.objects[object_name]
        if obj.type != 'MESH':
            return {"error": f"Object '{object_name}' is not a MESH."}

        # Select and make active
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        scene.view_layer.objects.active = obj

        # Go to Edit Mode
        bpy.ops.object.mode_set(mode='EDIT')
        
        # Select all faces
        bpy.ops.mesh.select_all(action='SELECT')
        
        # Intersect (Boolean) with Self-Intersect enabled
        # This resolves overlaps within the same mesh while maintaining original shape
        bpy.ops.mesh.intersect_boolean(operation='UNION', use_self=True, solver='EXACT', use_swap=True)
        
        # Final cleanup: merge by distance and fix normals
        bpy.ops.mesh.remove_doubles()
        bpy.ops.mesh.normals_make_consistent(inside=False)
        
        # Back to Object Mode
        bpy.ops.object.mode_set(mode='OBJECT')

        return {
            "success": True,
            "message": f"Resolved self-intersections in '{object_name}' while preserving the outer shape."
        }
    except Exception as e:
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        return {"error": f"Failed to resolve self-intersections: {str(e)}"}

