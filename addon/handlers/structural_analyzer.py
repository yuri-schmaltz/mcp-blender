"""Structural analyzer handler for BlenderMCP."""
from ..core.router import mcp_command

import bpy
import mathutils


@mcp_command(name="analyze_structural_properties", read_only=True)
def analyze_structural_properties(scene, object_name, material_preset="PLA"):
    """Calculate the estimated weight, center of mass, volume, and identify potential weak spots for 3D printing."""
    try:
        # Standard densities in kg/m3
        DENSITIES = {
            "PLA": 1240.0,
            "PETG": 1270.0,
            "ABS": 1040.0,
            "NYLON": 1150.0,
            "STEEL": 7850.0,
            "ALUMINUM": 2700.0,
        }

        material = material_preset.upper()
        if material not in DENSITIES:
            return {"error": f"Unknown material '{material_preset}'. Supported: PLA, PETG, ABS, NYLON, STEEL, ALUMINUM."}

        density = DENSITIES[material]

        if object_name not in scene.objects:
            return {"error": f"Object '{object_name}' not found."}

        obj = scene.objects[object_name]
        if obj.type != 'MESH':
            return {"error": f"Object '{object_name}' is not a MESH. Cannot analyze structural properties."}

        # Force a scene graph update to get correct evaluated dimensions
        bpy.context.view_layer.update()

        # Calculate bounding box volume (rough estimation)
        dims = obj.dimensions
        bbox_volume = dims.x * dims.y * dims.z # in m^3

        # Precise mesh volume calculation using evaluated depsgraph
        depsgraph = bpy.context.evaluated_depsgraph_get()
        eval_obj = obj.evaluated_get(depsgraph)
        mesh = eval_obj.to_mesh()

        # Center of Mass (average of vertices in world space)
        verts_world = [obj.matrix_world @ v.co for v in mesh.vertices]
        if not verts_world:
            return {"error": "Mesh has no vertices."}
        
        center_of_mass = sum(verts_world, mathutils.Vector()) / len(verts_world)

        # Estimate mesh volume using triangle signed volumes (divergence theorem)
        # For a watertight mesh, sum of signed volumes of tetrahedrons from origin to each face
        total_volume = 0.0
        for poly in mesh.polygons:
            if len(poly.vertices) >= 3:
                # Triangle fan for polygons
                v0 = verts_world[poly.vertices[0]]
                for i in range(1, len(poly.vertices) - 1):
                    v1 = verts_world[poly.vertices[i]]
                    v2 = verts_world[poly.vertices[i+1]]
                    # Signed volume of tetrahedron
                    vol = v0.dot(v1.cross(v2)) / 6.0
                    total_volume += vol

        total_volume = abs(total_volume) # Handle reversed normals gracefully

        # Mass calculation (Density * Volume)
        mass_kg = total_volume * density
        mass_g = mass_kg * 1000.0

        # Structural warnings / stress concentrators
        warnings = []
        
        # 1. Bounding box thickness check (thin wall check)
        min_dim_mm = min(dims.x, dims.y, dims.z) * 1000.0
        if min_dim_mm < 1.6: # Less than 4 wall perimeters (0.4mm nozzle)
            warnings.append(
                f"Thin section warning: The smallest dimension is {min_dim_mm:.2f}mm. "
                "Wall thickness under 1.6mm is fragile for functional parts under stress."
            )

        # 2. Aspect ratio warning
        max_dim = max(dims.x, dims.y, dims.z)
        if min(dims.x, dims.y, dims.z) > 0:
            aspect_ratio = max_dim / min(dims.x, dims.y, dims.z)
            if aspect_ratio > 10.0:
                warnings.append(
                    f"High aspect ratio ({aspect_ratio:.1f}): The part is very long/slender. "
                    "It is highly susceptible to bending or buckling under load."
                )

        # Estimate print filament cost (PLA average: $22/kg)
        cost_usd = mass_kg * 22.0

        return {
            "success": True,
            "object_name": object_name,
            "material": material,
            "density_kg_m3": density,
            "volume_cm3": total_volume * 1_000_000.0,
            "estimated_mass_grams": mass_g,
            "center_of_mass": [center_of_mass.x, center_of_mass.y, center_of_mass.z],
            "estimated_cost_usd": cost_usd,
            "structural_warnings": warnings,
            "message": f"Structural analysis complete for '{object_name}' ({material_preset}). Mass: {mass_g:.2f}g."
        }
    except Exception as e:
        return {"error": f"Failed to analyze structural properties: {str(e)}"}
