"""Blender UI components (panels and operators)."""


from .panel import MCP_PT_MainPanel
from .operators import MCP_OT_Executar

def register():
	import bpy
	bpy.utils.register_class(MCP_PT_MainPanel)
	bpy.utils.register_class(MCP_OT_Executar)

def unregister():
	import bpy
	bpy.utils.unregister_class(MCP_PT_MainPanel)
	bpy.utils.unregister_class(MCP_OT_Executar)

__all__ = ['panel', 'operators', 'register', 'unregister']
