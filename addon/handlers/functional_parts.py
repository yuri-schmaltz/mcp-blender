"""Functional part management for BlenderMCP."""

import bpy
import json

def mark_as_functional_part(scene, object_name, role="Generic", metadata=None):
    """Mark an object as a functional part with specific metadata."""
    try:
        if object_name not in scene.objects:
            return {"error": f"Object '{object_name}' not found."}
        
        obj = scene.objects[object_name]
        
        # Tag the object
        obj["mcp_functional_part"] = True
        obj["mcp_part_role"] = str(role)
        
        if metadata:
            if isinstance(metadata, dict):
                obj["mcp_part_metadata"] = json.dumps(metadata)
            else:
                obj["mcp_part_metadata"] = str(metadata)
        
        return {
            "success": True,
            "message": f"Object '{object_name}' marked as functional part ('{role}').",
            "metadata": obj.get("mcp_part_metadata", "{}")
        }
    except Exception as e:
        return {"error": f"Failed to mark part: {str(e)}"}

def list_functional_parts(scene):
    """List all functional parts in the scene with their properties."""
    try:
        parts = []
        for obj in scene.objects:
            if obj.get("mcp_functional_part"):
                role = obj.get("mcp_part_role", "Unknown")
                metadata_raw = obj.get("mcp_part_metadata", "{}")
                
                try:
                    metadata = json.loads(metadata_raw)
                except:
                    metadata = metadata_raw
                
                parts.append({
                    "name": obj.name,
                    "role": role,
                    "dimensions_mm": [d * 1000 for d in obj.dimensions],
                    "location": list(obj.location),
                    "metadata": metadata
                })
        
        return {
            "success": True,
            "parts_count": len(parts),
            "parts": parts
        }
    except Exception as e:
        return {"error": f"Failed to list parts: {str(e)}"}
