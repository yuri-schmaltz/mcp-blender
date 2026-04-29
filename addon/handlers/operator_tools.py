from ..core.router import mcp_command
import bpy
import json

@mcp_command(name="list_blender_operators", read_only=False)
def list_blender_operators(scene, filter_text=""):
    """
    List all available Blender operators, optionally filtered.
    """
    operators = []
    # Blender operators are in bpy.ops
    # We can iterate through the categories
    for category_name in dir(bpy.ops):
        if category_name.startswith("_"):
            continue
        
        category = getattr(bpy.ops, category_name)
        for op_name in dir(category):
            if op_name.startswith("_"):
                continue
            
            full_name = f"bpy.ops.{category_name}.{op_name}"
            if not filter_text or filter_text.lower() in full_name.lower():
                operators.append(full_name)
                
            if len(operators) > 200: # Limit output
                return {"operators": operators, "message": "Showing first 200 matches. Please use a filter to narrow down."}
                
    return {"operators": operators}

@mcp_command(name="get_operator_help", read_only=False)
def get_operator_help(scene, operator_name):
    """
    Get documentation for a specific Blender operator.
    """
    try:
        if not operator_name.startswith("bpy.ops."):
            return {"error": "Operator name must start with 'bpy.ops.'"}
        
        parts = operator_name.split(".")
        if len(parts) != 4:
            return {"error": "Operator name must be in the format 'bpy.ops.category.name'"}
        
        category_name = parts[2]
        op_name = parts[3]
        
        category = getattr(bpy.ops, category_name)
        op = getattr(category, op_name)
        
        # Get docstring and RNA info
        doc = op.get_rna_type().description
        # We could also get parameters here if we wanted to be very thorough
        # but the description is usually enough for an LLM.
        
        return {
            "operator": operator_name,
            "description": doc,
            "help_text": str(op.__doc__)
        }
    except Exception as e:
        return {"error": f"Could not get help for {operator_name}: {str(e)}"}
