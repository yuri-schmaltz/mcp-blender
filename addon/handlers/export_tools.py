"""Export and packaging tools for BlenderMCP."""
from ..core.router import mcp_command

import bpy
import os

@mcp_command(name="export_model", read_only=False)
def export_model(scene, filepath, format="GLTF", selection_only=True):
    """Export the scene or selected objects to a specific file format."""
    try:
        format = format.upper()
        
        # Ensure directory exists
        directory = os.path.dirname(filepath)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
            
        if format in ["GLB", "GLTF"]:
            bpy.ops.export_scene.gltf(
                filepath=filepath,
                use_selection=selection_only,
                export_format='GLB' if filepath.lower().endswith('.glb') else 'GLTF_EMBEDDED'
            )
        elif format == "STL":
            # Blender 4.x uses new STL exporter if available
            if hasattr(bpy.ops.wm, "stl_export"):
                bpy.ops.wm.stl_export(
                    filepath=filepath,
                    export_selected_objects=selection_only
                )
            else:
                # Fallback for older blender
                bpy.ops.export_mesh.stl(
                    filepath=filepath,
                    use_selection=selection_only
                )
        elif format == "OBJ":
            if hasattr(bpy.ops.wm, "obj_export"):
                bpy.ops.wm.obj_export(
                    filepath=filepath,
                    export_selected_objects=selection_only
                )
            else:
                bpy.ops.export_scene.obj(
                    filepath=filepath,
                    use_selection=selection_only
                )
        else:
            return {"error": f"Unsupported format '{format}'. Use GLTF, GLB, STL, or OBJ."}
            
        return {
            "success": True,
            "message": f"Successfully exported to {filepath} in {format} format."
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": f"Failed to export model: {str(e)}"}

@mcp_command(name="pack_all_resources", read_only=False)
def pack_all_resources(scene):
    """Pack all external data (textures, sounds, etc) into the .blend file."""
    try:
        bpy.ops.file.pack_all()
        return {
            "success": True,
            "message": "All external resources have been packed into the .blend file."
        }
    except Exception as e:
        return {"error": f"Failed to pack resources: {str(e)}"}
