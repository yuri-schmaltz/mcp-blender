"""Material setup and texture application tools for BlenderMCP."""
from ..core.router import mcp_command


import traceback

import bpy


@mcp_command(name="set_texture", read_only=False)
def set_texture(object_name, texture_id):
    """Apply a previously downloaded Polyhaven texture to an object by creating a new material"""
    try:
        # Get the object
        obj = bpy.data.objects.get(object_name)
        if not obj:
            return {"error": f"Object not found: {object_name}"}

        # Make sure object can accept materials
        if not hasattr(obj, "data") or not hasattr(obj.data, "materials"):
            return {"error": f"Object {object_name} cannot accept materials"}

        # Find all images related to this texture and ensure they're properly loaded
        texture_images = {}
        for img in bpy.data.images:
            if img.name.startswith(texture_id + "_"):
                # Extract the map type from the image name
                map_type = img.name.split("_")[-1].split(".")[0]

                # Force a reload of the image
                img.reload()

                # Ensure proper color space
                if map_type.lower() in ["color", "diffuse", "albedo"]:
                    try:
                        img.colorspace_settings.name = "sRGB"
                    except Exception:
                        pass
                else:
                    try:
                        img.colorspace_settings.name = "Non-Color"
                    except Exception:
                        pass

                # Ensure the image is packed
                if not img.packed_file:
                    img.pack()

                texture_images[map_type] = img

        if not texture_images:
            return {
                "error": f"No texture images found for: {texture_id}. Please download the texture first."
            }

        # Create a new material
        new_mat_name = f"{texture_id}_material_{object_name}"

        # Remove any existing material with this name to avoid conflicts
        existing_mat = bpy.data.materials.get(new_mat_name)
        if existing_mat:
            bpy.data.materials.remove(existing_mat)

        new_mat = bpy.data.materials.new(name=new_mat_name)
        new_mat.use_nodes = True

        # Set up the material nodes
        nodes = new_mat.node_tree.nodes
        links = new_mat.node_tree.links

        # Clear default nodes
        nodes.clear()

        # Create output node
        output = nodes.new(type="ShaderNodeOutputMaterial")
        output.location = (600, 0)

        # Create principled BSDF node
        principled = nodes.new(type="ShaderNodeBsdfPrincipled")
        principled.location = (300, 0)
        links.new(principled.outputs[0], output.inputs[0])

        # Add texture nodes based on available maps
        tex_coord = nodes.new(type="ShaderNodeTexCoord")
        tex_coord.location = (-800, 0)

        mapping = nodes.new(type="ShaderNodeMapping")
        mapping.location = (-600, 0)
        mapping.vector_type = "TEXTURE"
        links.new(tex_coord.outputs["UV"], mapping.inputs["Vector"])

        # Position offset for texture nodes
        x_pos = -400
        y_pos = 300

        # Connect different texture maps
        for map_type, image in texture_images.items():
            tex_node = nodes.new(type="ShaderNodeTexImage")
            tex_node.location = (x_pos, y_pos)
            tex_node.image = image

            # Set color space based on map type
            if map_type.lower() in ["color", "diffuse", "albedo"]:
                try:
                    tex_node.image.colorspace_settings.name = "sRGB"
                except Exception:
                    pass
            else:
                try:
                    tex_node.image.colorspace_settings.name = "Non-Color"
                except Exception:
                    pass

            links.new(mapping.outputs["Vector"], tex_node.inputs["Vector"])

            # Connect to appropriate input on Principled BSDF
            if map_type.lower() in ["color", "diffuse", "albedo"]:
                links.new(tex_node.outputs["Color"], principled.inputs["Base Color"])
            elif map_type.lower() in ["roughness", "rough"]:
                links.new(tex_node.outputs["Color"], principled.inputs["Roughness"])
            elif map_type.lower() in ["metallic", "metalness", "metal"]:
                links.new(tex_node.outputs["Color"], principled.inputs["Metallic"])
            elif map_type.lower() in ["normal", "nor", "dx", "gl"]:
                # Add normal map node
                normal_map = nodes.new(type="ShaderNodeNormalMap")
                normal_map.location = (x_pos + 200, y_pos)
                links.new(tex_node.outputs["Color"], normal_map.inputs["Color"])
                links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])
            elif map_type.lower() in ["displacement", "disp", "height"]:
                # Add displacement node
                disp_node = nodes.new(type="ShaderNodeDisplacement")
                disp_node.location = (x_pos + 200, y_pos - 200)
                disp_node.inputs["Scale"].default_value = 0.1
                links.new(tex_node.outputs["Color"], disp_node.inputs["Height"])
                links.new(disp_node.outputs["Displacement"], output.inputs["Displacement"])

            y_pos -= 250

        # Second pass: Connect nodes with proper handling for special cases
        texture_nodes = {}
        for node in nodes:
            if node.type == "TEX_IMAGE" and node.image:
                for map_type, image in texture_images.items():
                    if node.image == image:
                        texture_nodes[map_type] = node
                        break

        # Handle base color
        for map_name in ["color", "diffuse", "albedo"]:
            if map_name in texture_nodes:
                links.new(texture_nodes[map_name].outputs["Color"], principled.inputs["Base Color"])
                break

        # Handle roughness
        for map_name in ["roughness", "rough"]:
            if map_name in texture_nodes:
                links.new(texture_nodes[map_name].outputs["Color"], principled.inputs["Roughness"])
                break

        # Handle metallic
        for map_name in ["metallic", "metalness", "metal"]:
            if map_name in texture_nodes:
                links.new(texture_nodes[map_name].outputs["Color"], principled.inputs["Metallic"])
                break

        # Handle normal maps
        for map_name in ["gl", "dx", "nor"]:
            if map_name in texture_nodes:
                normal_map_node = nodes.new(type="ShaderNodeNormalMap")
                normal_map_node.location = (100, 100)
                links.new(texture_nodes[map_name].outputs["Color"], normal_map_node.inputs["Color"])
                links.new(normal_map_node.outputs["Normal"], principled.inputs["Normal"])
                break

        # Handle displacement
        for map_name in ["displacement", "disp", "height"]:
            if map_name in texture_nodes:
                disp_node = nodes.new(type="ShaderNodeDisplacement")
                disp_node.location = (300, -200)
                disp_node.inputs["Scale"].default_value = 0.1
                links.new(texture_nodes[map_name].outputs["Color"], disp_node.inputs["Height"])
                links.new(disp_node.outputs["Displacement"], output.inputs["Displacement"])
                break

        # Handle ARM texture
        if "arm" in texture_nodes:
            separate_rgb = nodes.new(type="ShaderNodeSeparateRGB")
            separate_rgb.location = (-200, -100)
            links.new(texture_nodes["arm"].outputs["Color"], separate_rgb.inputs["Image"])

            if not any(map_name in texture_nodes for map_name in ["roughness", "rough"]):
                links.new(separate_rgb.outputs["G"], principled.inputs["Roughness"])

            if not any(map_name in texture_nodes for map_name in ["metallic", "metalness", "metal"]):
                links.new(separate_rgb.outputs["B"], principled.inputs["Metallic"])

            # AO mix
            base_color_node = None
            for map_name in ["color", "diffuse", "albedo"]:
                if map_name in texture_nodes:
                    base_color_node = texture_nodes[map_name]
                    break

            if base_color_node:
                mix_node = nodes.new(type="ShaderNodeMixRGB")
                mix_node.location = (100, 200)
                mix_node.blend_type = "MULTIPLY"
                mix_node.inputs["Fac"].default_value = 0.8
                for link in base_color_node.outputs["Color"].links:
                    if link.to_socket == principled.inputs["Base Color"]:
                        links.remove(link)
                links.new(base_color_node.outputs["Color"], mix_node.inputs[1])
                links.new(separate_rgb.outputs["R"], mix_node.inputs[2])
                links.new(mix_node.outputs["Color"], principled.inputs["Base Color"])

        # Handle AO separate
        if "ao" in texture_nodes:
            base_color_node = None
            for map_name in ["color", "diffuse", "albedo"]:
                if map_name in texture_nodes:
                    base_color_node = texture_nodes[map_name]
                    break
            if base_color_node:
                mix_node = nodes.new(type="ShaderNodeMixRGB")
                mix_node.location = (100, 200)
                mix_node.blend_type = "MULTIPLY"
                mix_node.inputs["Fac"].default_value = 0.8
                for link in base_color_node.outputs["Color"].links:
                    if link.to_socket == principled.inputs["Base Color"]:
                        links.remove(link)
                links.new(base_color_node.outputs["Color"], mix_node.inputs[1])
                links.new(texture_nodes["ao"].outputs["Color"], mix_node.inputs[2])
                links.new(mix_node.outputs["Color"], principled.inputs["Base Color"])

        # Clear existing and apply
        while len(obj.data.materials) > 0:
            obj.data.materials.pop(index=0)
        obj.data.materials.append(new_mat)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.context.view_layer.update()

        return {
            "success": True,
            "message": f"Applied texture {texture_id} to {object_name}",
            "material": new_mat.name,
            "maps": list(texture_images.keys()),
        }

    except Exception as e:
        traceback.print_exc()
        return {"error": f"Failed to apply texture: {str(e)}"}
