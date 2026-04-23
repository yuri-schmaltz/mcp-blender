"""MCP Tool Schemas for BlenderMCP. 
Defines the input parameters for each tool to help LLMs generate correct calls.
"""

TOOL_SCHEMAS = {
    "get_scene_info": {
        "description": "Get general information about the current Blender scene (objects, collections, render settings).",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    "transform_object": {
        "description": "Move, rotate or scale an object.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the object to transform"},
                "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3, "description": "New location (x, y, z)"},
                "rotation": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3, "description": "New rotation in degrees (x, y, z)"},
                "scale": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3, "description": "New scale (x, y, z)"},
                "relative": {"type": "boolean", "description": "If true, transforms are relative to current values", "default": False}
            },
            "required": ["name"]
        }
    },
    "add_primitive": {
        "description": "Add a new primitive object to the scene.",
        "parameters": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["cube", "sphere", "plane", "cylinder", "cone", "torus", "monkey"], "description": "Type of primitive"},
                "name": {"type": "string", "description": "Name for the new object"},
                "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "scale": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3}
            },
            "required": ["type"]
        }
    },
    "download_polyhaven_asset": {
        "description": "Download and import an asset from Poly Haven.",
        "parameters": {
            "type": "object",
            "properties": {
                "asset_id": {"type": "string", "description": "ID of the asset (e.g., 'forest_slope')"},
                "asset_type": {"type": "string", "enum": ["hdris", "textures", "models"], "description": "Type of asset"},
                "resolution": {"type": "string", "enum": ["1k", "2k", "4k", "8k"], "default": "2k"}
            },
            "required": ["asset_id", "asset_type"]
        }
    },
    "execute_code": {
        "description": "Execute arbitrary Python code in Blender. Use with caution.",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"}
            },
            "required": ["code"]
        }
    }
    # More schemas can be added here...
}

def get_tools_list():
    """Return a list of tools formatted for MCP discovery."""
    return [
        {"name": name, "description": schema["description"], "inputSchema": schema["parameters"]}
        for name, schema in TOOL_SCHEMAS.items()
    ]
