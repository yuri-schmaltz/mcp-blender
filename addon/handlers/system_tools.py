import io
from contextlib import redirect_stdout
import bpy

from ..core.router import mcp_command

def get_prefs():
    # Use fallback robust lookup for preferences since we are inside a handler
    # We will try to find the MCP add-on package name dynamically
    for name, addon in bpy.context.preferences.addons.items():
        if hasattr(addon, "preferences") and hasattr(addon.preferences, "allow_code_execution"):
            return addon.preferences
    return None

@mcp_command(name="execute_code", read_only=False)
def execute_code(code: str, scene=None):
    prefs = get_prefs()
    if prefs and not getattr(prefs, "allow_code_execution", False):
        return {"error": "Code execution blocked by global preferences. Enable it in Edit > Preferences > Addons > Blender MCP."}
    try:
        namespace = {"bpy": bpy}
        capture_buffer = io.StringIO()
        with redirect_stdout(capture_buffer):
            exec(code, namespace)
        return {"executed": True, "result": capture_buffer.getvalue()}
    except Exception as e:
        return {"error": str(e)}

@mcp_command(name="list_tools", read_only=True)
def list_tools(scene=None):
    try:
        from .. import tool_schemas
        return tool_schemas.get_tools_list()
    except Exception as e:
        return {"error": f"Tool schemas not available: {e}"}
