# operators.py - Exemplo de operador com feedback e acessibilidade
import bpy
from .tokens import COLORS

class MCP_OT_Executar(bpy.types.Operator):
    bl_idname = "mcp.executar"
    bl_label = "Executar Ação"
    bl_description = "Executa uma ação do MCP com feedback acessível"

    def execute(self, context):
        self.report({'INFO'}, "Ação executada com sucesso!")
        return {'FINISHED'}

# Checklist de acessibilidade aplicado:
# - Label e descrição claros
# - Feedback visual via self.report
# - Integração com painel principal
