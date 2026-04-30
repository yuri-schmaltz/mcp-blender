import bpy
from ..ui import UI_CLASSES
from .server_manager import BlenderMCPServerManager

def register_all():
    """Register all addon components in the correct order."""
    # 1. Register Preferences
    # Note: BlenderMCPPreferences is usually registered by addon.py/register()
    
    # 2. Register UI Classes
    print(f"BlenderMCP: Registering {len(UI_CLASSES)} UI classes...")
    for cls in UI_CLASSES:
        try:
            bpy.utils.register_class(cls)
            print(f"  [OK] Registered: {cls.__name__}")
        except Exception as e:
            print(f"  [ERROR] Failed to register {cls}: {e}")
    
    # 3. Initialize Server Manager
    # This will be handled by addon.py for now to avoid complexity
    
    print("BlenderMCP: Core components registered.")

def unregister_all():
    """Unregister all addon components and cleanup."""
    # 1. Unregister UI Classes
    for cls in reversed(UI_CLASSES):
        try:
            if hasattr(cls, "bl_rna"):
                bpy.utils.unregister_class(cls)
        except Exception:
            pass

    # 2. Cleanup Scene properties dynamically
    mcp_props = [p for p in dir(bpy.types.Scene) if p.startswith("blendermcp_")]
    for prop in mcp_props:
        try:
            delattr(bpy.types.Scene, prop)
        except Exception:
            pass
            
    print("BlenderMCP: Core components unregistered.")
