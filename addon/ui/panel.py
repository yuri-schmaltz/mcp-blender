"""BlenderMCP UI Panel - redesigned with collapsible sub-panels for better UX."""

import os
import sys

import bpy
import importlib.util as _iu


def _get_addon_module():
    """Load addon.py via filesystem (works in any Blender loading mode)."""
    addon_py = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "addon.py")
    for mod in sys.modules.values():
        if hasattr(mod, "__file__") and mod.__file__ and os.path.abspath(mod.__file__) == os.path.abspath(addon_py):
            return mod
    spec = _iu.spec_from_file_location("_blendermcp_addon_ref_panel", addon_py)
    mod = _iu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# =============================================================================
# Main Panel: Connection status + Connect/Disconnect
# =============================================================================
class BLENDERMCP_PT_Panel(bpy.types.Panel):
    bl_label = "Blender MCP"
    bl_idname = "BLENDERMCP_PT_Panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BlenderMCP"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        if scene.blendermcp_server_running:
            # --- Connected state ---
            status_row = layout.row()
            status_row.alert = False
            status_row.label(text=f"Connected  ·  Port {scene.blendermcp_port}", icon="CHECKMARK")

            layout.separator(factor=0.5)
            disconnect_row = layout.row(align=True)
            disconnect_row.scale_y = 1.4
            disconnect_row.operator("blendermcp.stop_server", text="Disconnect", icon="CANCEL")
        else:
            # --- Disconnected state ---
            status_row = layout.row()
            status_row.alert = True
            status_row.label(text="Disconnected", icon="ERROR")

            layout.separator(factor=0.5)
            layout.prop(scene, "blendermcp_port")

            layout.separator(factor=0.5)
            connect_row = layout.row(align=True)
            connect_row.scale_y = 1.6
            connect_row.operator("blendermcp.start_server", text="Connect to LLM", icon="PLAY")


# =============================================================================
# Sub-Panel: Integrations (Poly Haven, Sketchfab, Code Execution)
# =============================================================================
class BLENDERMCP_PT_Integrations(bpy.types.Panel):
    bl_label = "Integrations"
    bl_idname = "BLENDERMCP_PT_Integrations"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BlenderMCP"
    bl_parent_id = "BLENDERMCP_PT_Panel"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # Poly Haven
        col = layout.column(align=True)
        col.prop(scene, "blendermcp_use_polyhaven", text="Poly Haven Assets", icon="WORLD")
        if scene.blendermcp_use_polyhaven:
            info = col.row()
            info.label(text="HDRIs, textures & models from polyhaven.com", icon="INFO")

        layout.separator(factor=0.3)

        # AmbientCG
        col = layout.column(align=True)
        col.prop(scene, "blendermcp_use_ambientcg", text="AmbientCG Assets", icon="MATERIAL")
        if scene.blendermcp_use_ambientcg:
            info = col.row()
            info.label(text="PBR textures from ambientcg.com", icon="INFO")

        layout.separator(factor=0.3)

        # Sketchfab
        col = layout.column(align=True)
        col.prop(scene, "blendermcp_use_sketchfab", text="Sketchfab Assets", icon="MESH_MONKEY")
        if scene.blendermcp_use_sketchfab:
            col.prop(scene, "blendermcp_sketchfab_api_key", text="API Key")
            warn = col.row()
            warn.alert = True
            warn.label(text="Key is saved in .blend file", icon="ERROR")

        layout.separator(factor=0.3)

        # Code Execution
        col = layout.column(align=True)
        col.prop(scene, "blendermcp_allow_code_execution", text="Remote Code Execution", icon="SCRIPT")
        if scene.blendermcp_allow_code_execution:
            warn = col.row()
            warn.alert = True
            warn.label(text="LLM can execute arbitrary Python!", icon="ERROR")


# =============================================================================
# Sub-Panel: Client Setup (first-time configuration)
# =============================================================================
class BLENDERMCP_PT_ClientSetup(bpy.types.Panel):
    bl_label = "Client Setup"
    bl_idname = "BLENDERMCP_PT_ClientSetup"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BlenderMCP"
    bl_parent_id = "BLENDERMCP_PT_Panel"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # Step 1: Choose client
        layout.label(text="1. Choose your LLM client:", icon="QUESTION")
        layout.prop(scene, "blendermcp_client_target", text="")

        layout.separator(factor=0.3)

        # Step 2: Copy config
        layout.label(text="2. Copy config to clipboard:", icon="COPYDOWN")
        layout.operator(
            "blendermcp.copy_mcp_client_config",
            text="Copy MCP Config",
            icon="COPYDOWN",
        )

        layout.separator(factor=0.3)

        # Step 3: Run server
        layout.label(text="3. Start the MCP bridge:", icon="PLAY")
        layout.operator(
            "blendermcp.run_mcp_terminal_server",
            text="Run MCP Server in Terminal",
            icon="CONSOLE",
        )


# =============================================================================
# Sub-Panel: Tools (diagnostics, logs, deps)
# =============================================================================
class BLENDERMCP_PT_Tools(bpy.types.Panel):
    bl_label = "Tools"
    bl_idname = "BLENDERMCP_PT_Tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BlenderMCP"
    bl_parent_id = "BLENDERMCP_PT_Panel"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout

        col = layout.column(align=True)
        col.operator("blendermcp.install_dependencies", text="Install Dependencies", icon="IMPORT")
        col.operator("blendermcp.health_check", text="Health Check", icon="CHECKMARK")
        col.operator("blendermcp.open_logs", text="Open Logs", icon="TEXT")


# =============================================================================
# Sub-Panel: Status (last action + cache)
# =============================================================================
class BLENDERMCP_PT_Status(bpy.types.Panel):
    bl_label = "Status"
    bl_idname = "BLENDERMCP_PT_Status"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BlenderMCP"
    bl_parent_id = "BLENDERMCP_PT_Panel"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # Last action
        if scene.blendermcp_last_action:
            icon = "CHECKMARK" if scene.blendermcp_last_action_ok else "ERROR"
            row = layout.row()
            row.alert = not scene.blendermcp_last_action_ok
            row.label(text=scene.blendermcp_last_action, icon=icon)
            layout.label(text=scene.blendermcp_last_action_at, icon="TIME")
            if scene.blendermcp_last_action_details:
                layout.label(text=scene.blendermcp_last_action_details[:60])
        else:
            layout.label(text="No actions yet", icon="INFO")

        layout.separator(factor=0.5)

        # Cache info
        layout.label(text="Asset Cache", icon="FILE_CACHE")
        try:
            addon_mod = _get_addon_module()
            cache_size, file_count = addon_mod._asset_cache.get_cache_size()
        except Exception:
            cache_size, file_count = 0, 0

        size_mb = cache_size / (1024 * 1024)
        row = layout.row(align=True)
        row.label(text=f"{file_count} files  ·  {size_mb:.1f} MB")
        row.operator("blendermcp.clear_cache", text="Clear", icon="TRASH")


# All panel classes in registration order (parent first, then children)
PANEL_CLASSES = [
    BLENDERMCP_PT_Panel,
    BLENDERMCP_PT_Integrations,
    BLENDERMCP_PT_ClientSetup,
    BLENDERMCP_PT_Tools,
    BLENDERMCP_PT_Status,
]
