"""Procedural modeling tools for BlenderMCP."""


import bpy


def generate_tire_treads(scene, wheel_name, pattern='OFFROAD'):
    """Generate procedural tire treads on a cylindrical wheel mesh."""
    try:
        if wheel_name not in scene.objects:
            return {"error": f"Wheel object '{wheel_name}' not found."}

        obj = scene.objects[wheel_name]
        if obj.type != 'MESH':
            return {"error": f"Object '{wheel_name}' is not a MESH."}

        # Simple tread generation via Subdivision + Displace
        # For a more advanced version, we could use Geometry Nodes

        # Ensure object is active
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        scene.view_layer.objects.active = obj

        # 1. Add Subdivision Surface for detail
        subdiv = obj.modifiers.new(name="Tread_Subdiv", type='SUBSURF')
        subdiv.levels = 2
        subdiv.render_levels = 3

        # 2. Create a procedural texture for the tread
        tex_name = f"TireTread_{pattern}"
        if tex_name not in bpy.data.textures:
            tex = bpy.data.textures.new(name=tex_name, type='VORONOI')
            if pattern == 'OFFROAD':
                tex.voronoi.distance_metric = 'DISTANCE'
                tex.noise_scale = 0.05
            else: # STREET
                tex.type = 'WOOD'
                tex.wood_type = 'BANDNOISE'
                tex.noise_scale = 0.1
        else:
            tex = bpy.data.textures[tex_name]

        # 3. Add Displace modifier
        displace = obj.modifiers.new(name="Tread_Displace", type='DISPLACE')
        displace.texture = tex
        displace.strength = 0.01 if pattern == 'STREET' else 0.03
        displace.texture_coords = 'OBJECT'

        return {
            "success": True,
            "message": f"Generated {pattern} treads on '{wheel_name}' using modifiers.",
            "modifiers_added": ["Tread_Subdiv", "Tread_Displace"]
        }
    except Exception as e:
        return {"error": f"Failed to generate treads: {str(e)}"}
