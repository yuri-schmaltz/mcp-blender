"""AmbientCG API handler for downloading PBR materials."""

import os
import shutil
import tempfile
import zipfile

import bpy

# Use the robust networking module
from ..utils.network import friendly_error, log_asset_download, robust_get


def get_ambientcg_status(scene):
    """Get the current status of AmbientCG integration"""
    enabled = scene.blendermcp_use_ambientcg
    if enabled:
        return {
            "enabled": True,
            "message": "AmbientCG integration is enabled and ready to use.",
        }
    else:
        return {
            "enabled": False,
            "message": """AmbientCG integration is currently disabled. To enable it:
                        1. In the 3D Viewport, find the BlenderMCP panel in the sidebar (press N if hidden)
                        2. Open 'Integrations' panel
                        3. Check the 'AmbientCG Assets' checkbox
                        4. Restart the connection to your LLM client""",
        }


def search_ambientcg_materials(scene, query="", limit=20):
    """Search for materials on AmbientCG based on query"""
    try:
        if not scene.blendermcp_use_ambientcg:
            return {"error": "AmbientCG integration is disabled. Please enable it in the BlenderMCP panel."}

        url = "https://ambientcg.com/api/v2/full_json"
        params = {
            "type": "Material",
            "limit": limit,
            "include": "downloadData",
        }
        if query:
            params["q"] = query

        response = robust_get(url, params=params)
        if response.status_code == 200:
            data = response.json()

            # Format the output for the LLM
            results = []
            for asset in data.get("foundAssets", []):
                resolutions = []
                for dl in asset.get("downloadFolders", {}).get("default", {}).get("downloadFiletypeCategories", {}).get("zip", {}).get("downloads", []):
                    resolutions.append(dl.get("attribute"))

                results.append({
                    "assetId": asset.get("assetId"),
                    "tags": asset.get("tags", []),
                    "available_resolutions": [r for r in resolutions if r]
                })

            return {
                "results": results,
                "total_count": data.get("numberOfResults", 0),
                "returned_count": len(results),
            }
        else:
            return {"error": f"AmbientCG API returned status {response.status_code}. Try again later."}
    except Exception as e:
        return friendly_error("AmbientCG search", e)


def download_ambientcg_material(scene, asset_id, resolution="2K", file_format="JPG", progress_tracker=None):
    """Download and set up an AmbientCG material"""
    try:
        if not scene.blendermcp_use_ambientcg:
            return {"error": "AmbientCG integration is disabled. Please enable it in the BlenderMCP panel."}

        # Validate resolution formatting (AmbientCG uses uppercase K: 1K, 2K, 4K, 8K)
        # LLMs often pass "2k" instead of "2K"
        resolution = resolution.upper()
        file_format = file_format.upper()

        # Determine actual download URL
        # Format usually: https://ambientcg.com/get?file=AssetId_Resolution-Format.zip
        # e.g. Wood066_2K-JPG.zip
        zip_filename = f"{asset_id}_{resolution}-{file_format}.zip"
        download_url = f"https://ambientcg.com/get?file={zip_filename}"

        # Setup temp path
        temp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(temp_dir, zip_filename)
        extract_dir = os.path.join(temp_dir, asset_id)
        os.makedirs(extract_dir, exist_ok=True)

        try:
            # Download ZIP
            operation_id = f"ambientcg_{asset_id}_{resolution}"
            response = robust_get(download_url, stream=True)

            if response.status_code == 404:
                # Try fallback (AmbientCG sometimes uses different naming or the resolution is missing)
                return {"error": f"Material '{asset_id}' not found in {resolution}-{file_format}. Try checking the available resolutions from the search results, or try '1K' or '2K' PNG."}

            if response.status_code != 200:
                return {"error": f"Failed to download material: {response.status_code}"}

            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0

            if progress_tracker:
                progress_tracker.start_operation(operation_id, total_size)

            with open(zip_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_tracker:
                            progress_tracker.update_progress(operation_id, downloaded)

            if progress_tracker:
                progress_tracker.complete_operation(operation_id)

            # Extract ZIP
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(extract_dir)

            # Look for PBR maps
            extracted_files = os.listdir(extract_dir)
            maps = {}
            map_types = {
                "Color": ["Color", "BaseColor", "Diffuse"],
                "Normal": ["NormalGL", "Normal"],  # Prefer OpenGL normal map for Blender
                "Roughness": ["Roughness"],
                "AO": ["AmbientOcclusion", "AO"],
                "Displacement": ["Displacement", "Height"],
                "Metallic": ["Metalness", "Metallic"]
            }

            for file in extracted_files:
                filepath = os.path.join(extract_dir, file)
                name_without_ext = os.path.splitext(file)[0]

                # Ex: Wood066_2K-JPG_Color.jpg -> split by _
                parts = name_without_ext.split("_")
                if len(parts) >= 2:
                    map_suffix = parts[-1]  # 'Color', 'NormalGL', etc.

                    for map_key, aliases in map_types.items():
                        if map_suffix in aliases and map_key not in maps:
                            maps[map_key] = filepath
                            break

            if "Color" not in maps and "Normal" not in maps:
                 return {"error": f"Downloaded the archive but could not identify PBR texture maps. Found files: {extracted_files}"}

            # Create Material in Blender
            mat_name = f"ACG_{asset_id}_{resolution}"
            mat = bpy.data.materials.new(name=mat_name)
            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links

            nodes.clear()

            # Set up Principled BSDF
            principled = nodes.new(type="ShaderNodeBsdfPrincipled")
            principled.location = (0, 0)

            # Set up Material Output
            output = nodes.new(type="ShaderNodeOutputMaterial")
            output.location = (300, 0)
            links.new(principled.outputs["BSDF"], output.inputs["Surface"])

            # Set up Coordinates
            tex_coord = nodes.new(type="ShaderNodeTexCoord")
            tex_coord.location = (-1000, 0)
            mapping = nodes.new(type="ShaderNodeMapping")
            mapping.location = (-800, 0)
            links.new(tex_coord.outputs["UV"], mapping.inputs["Vector"])

            # Map: Color
            if "Color" in maps:
                img_node = nodes.new(type="ShaderNodeTexImage")
                img_node.location = (-500, 300)
                img = bpy.data.images.load(maps["Color"])
                img.pack()
                img_node.image = img
                img_node.name = "Color_Map"
                links.new(mapping.outputs["Vector"], img_node.inputs["Vector"])
                links.new(img_node.outputs["Color"], principled.inputs["Base Color"])

            # Map: Roughness
            if "Roughness" in maps:
                img_node = nodes.new(type="ShaderNodeTexImage")
                img_node.location = (-500, 0)
                img = bpy.data.images.load(maps["Roughness"])
                img.pack()
                img_node.image = img
                img_node.image.colorspace_settings.name = "Non-Color"
                img_node.name = "Roughness_Map"
                links.new(mapping.outputs["Vector"], img_node.inputs["Vector"])
                links.new(img_node.outputs["Color"], principled.inputs["Roughness"])

            # Map: Metallic
            if "Metallic" in maps:
                img_node = nodes.new(type="ShaderNodeTexImage")
                img_node.location = (-500, -300)
                img = bpy.data.images.load(maps["Metallic"])
                img.pack()
                img_node.image = img
                img_node.image.colorspace_settings.name = "Non-Color"
                img_node.name = "Metallic_Map"
                links.new(mapping.outputs["Vector"], img_node.inputs["Vector"])
                links.new(img_node.outputs["Color"], principled.inputs["Metallic"])

            # Map: Normal
            if "Normal" in maps:
                img_node = nodes.new(type="ShaderNodeTexImage")
                img_node.location = (-500, -600)
                img = bpy.data.images.load(maps["Normal"])
                img.pack()
                img_node.image = img
                img_node.image.colorspace_settings.name = "Non-Color"
                img_node.name = "Normal_Map"

                normal_map_node = nodes.new(type="ShaderNodeNormalMap")
                normal_map_node.location = (-200, -600)

                links.new(mapping.outputs["Vector"], img_node.inputs["Vector"])
                links.new(img_node.outputs["Color"], normal_map_node.inputs["Color"])
                links.new(normal_map_node.outputs["Normal"], principled.inputs["Normal"])

            # Log the successful download
            log_asset_download("ambientcg", asset_id, "material", resolution)

            # Apply to selected objects if any
            applied_to = []
            if bpy.context.selected_objects:
                for obj in bpy.context.selected_objects:
                    if obj.type == "MESH":
                        if len(obj.data.materials) == 0:
                            obj.data.materials.append(mat)
                        else:
                            obj.data.materials[obj.active_material_index] = mat
                        applied_to.append(obj.name)

            msg = f"Material {asset_id} imported successfully as '{mat_name}'."
            if applied_to:
                msg += f" Applied to {len(applied_to)} selected objects."
            else:
                msg += " (Not applied to any objects since none were selected)."

            return {
                "success": True,
                "message": msg,
                "material_name": mat_name,
                "maps_loaded": list(maps.keys())
            }

        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"error": f"Failed to set up material in Blender: {str(e)}"}
        finally:
            # Cleanup temp directory
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                print(f"Warning: Failed to cleanup ambientcg temp dir {temp_dir}: {str(e)}")

    except Exception as e:
        return friendly_error("AmbientCG download", e)
