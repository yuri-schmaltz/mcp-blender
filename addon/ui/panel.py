# panel.py - Exemplo de painel com tokens e acessibilidade
from .tokens import COLORS, SPACING, FONT_SIZES
import bpy

class MCP_PT_MainPanel(bpy.types.Panel):
    bl_label = "MCP Principal"
    bl_idname = "MCP_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'MCP'

    def draw(self, context):
        layout = self.layout
        # Exemplo de uso de tokens
        row = layout.row()
        row.label(text="Bem-vindo ao MCP!", icon='INFO')
        # Acessibilidade: label claro, contraste, tamanho de fonte
        row = layout.row()
        row.label(text="Ação:")
        row = layout.row()
        row.operator("mcp.executar", text="Executar", icon='PLAY')

# Checklist de acessibilidade aplicado:
# - Labels claros
# - Icones para reforço visual
# - Componentes com espaçamento padrão
# - Não depende só de cor
# - Navegação por teclado padrão Blender
