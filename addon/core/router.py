import inspect
import traceback
import bpy
import logging

logger = logging.getLogger("BlenderMCP.Router")

_COMMAND_REGISTRY = {}

def mcp_command(name=None, read_only=False):
    """
    Decorator to register an MCP command handler.
    :param name: Optional explicit command name. Defaults to the function name.
    :param read_only: If True, skips pushing an undo step in Blender.
    """
    def decorator(func):
        cmd_name = name if name else func.__name__
        _COMMAND_REGISTRY[cmd_name] = {
            "func": func,
            "read_only": read_only
        }
        return func
    return decorator

def execute_command(command: dict):
    """
    Executes a registered command by its type.
    """
    cmd_type = command.get("type")
    params = command.get("params", {})
    
    if not cmd_type:
        return {"status": "error", "message": "Command type missing"}
        
    # Temporary fallback/intercept for execute_code and list_tools that are special
    # We will register them manually or directly intercept them here if they don't use the decorator yet.
    cmd_info = _COMMAND_REGISTRY.get(cmd_type)
    
    if not cmd_info:
        return {"status": "error", "message": f"Unknown command type: {cmd_type}"}
        
    try:
        func = cmd_info["func"]
        
        # Inject scene if the handler expects it
        sig = inspect.signature(func)
        if "scene" in sig.parameters and "scene" not in params:
            params["scene"] = bpy.context.scene
            
        result = func(**params)
        
        # Undo history
        if not cmd_info["read_only"]:
            try:
                msg = f"MCP: {cmd_type}"
                if params:
                    first_val = next(iter(params.values()))
                    msg += f" ({str(first_val)[:20]})"
                bpy.ops.ed.undo_push(message=msg)
            except Exception as e:
                logger.debug(f"Failed to push undo step: {e}")
                
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"Error executing {cmd_type}: {e}")
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

def get_registered_commands():
    return list(_COMMAND_REGISTRY.keys())
