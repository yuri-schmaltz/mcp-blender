"""BlenderMCP UI Panel - redesigned with collapsible sub-panels for better UX."""

import os
import sys

import bpy
import importlib.util as _iu


def _get_addon_module():
    """Load the main addon module safely in all Blender loading modes."""
    # 1. Try via package if available (standard Extension mode)
    if __package__:
        try:
            root_package = __package__.split('.')[0]
            if root_package in sys.modules:
                return sys.modules[root_package]
        except Exception:
            pass

    # 2. Fallback to filesystem detection (Repo mode or non-standard install)
    # addon/ui/panel.py -> addon/ui -> addon -> project_root
    ui_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(ui_dir))
    
    # Candidate files for the main entry point
    for cand in ["addon.py", "__init__.py"]:
        addon_py = os.path.join(project_root, cand)
        if os.path.exists(addon_py):
            # Check if already loaded by Blender
            for mod in sys.modules.values():
                if hasattr(mod, "__file__") and mod.__file__ and os.path.abspath(mod.__file__) == os.path.abspath(addon_py):
                    return mod
            
            # Load dynamic spec if not already in sys.modules
            spec = _iu.spec_from_file_location("_blendermcp_addon_ref_panel", addon_py)
            mod = _iu.module_from_spec(spec)
            if __package__:
                mod.__package__ = __package__
            spec.loader.exec_module(mod)
            return mod
            
    raise ImportError("Could not locate BlenderMCP main module (addon.py or __init__.py)")

# Import i18n
_i18n_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "utils", "i18n.py")
_i18n_spec = _iu.spec_from_file_location("_blendermcp_i18n_panel", _i18n_path)
_i18n = _iu.module_from_spec(_i18n_spec)
_i18n_spec.loader.exec_module(_i18n)
t = _i18n.t


# =============================================================================
# Main Panel: Connection status + Connect/Disconnect
# =============================================================================
class BLENDERMCP_PT_Panel(bpy.types.Panel):
    bl_label = "Blender MCP" # This is a static property, hard to localize dynamically in class def
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
            status_row.label(text=t("status_connected", port=scene.blendermcp_port), icon="CHECKMARK")

            layout.separator(factor=0.5)
            disconnect_row = layout.row(align=True)
            disconnect_row.scale_y = 1.4
            disconnect_row.operator("blendermcp.stop_server", text=t("btn_disconnect"), icon="CANCEL")
        else:
            # --- Disconnected state ---
            status_row = layout.row()
            status_row.alert = True
            status_row.label(text=t("status_disconnected"), icon="ERROR")

            layout.separator(factor=0.5)
            layout.prop(scene, "blendermcp_port")

            layout.separator(factor=0.5)
            connect_row = layout.row(align=True)
            connect_row.scale_y = 1.6
            connect_row.operator("blendermcp.start_server", text=t("btn_connect"), icon="PLAY")


# =============================================================================
# Sub-Panel: Integrations (Poly Haven, Sketchfab, Code Execution)
# =============================================================================
class BLENDERMCP_PT_Integrations(bpy.types.Panel):
    bl_label = t("panel_integrations_label")
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
        col.prop(scene, "blendermcp_use_polyhaven", text=t("prop_polyhaven_assets"), icon="WORLD")
        if scene.blendermcp_use_polyhaven:
            info = col.row()
            info.label(text=t("info_polyhaven_assets"), icon="INFO")

        layout.separator(factor=0.3)

        # AmbientCG
        col = layout.column(align=True)
        col.prop(scene, "blendermcp_use_ambientcg", text=t("prop_ambientcg_assets"), icon="MATERIAL")
        if scene.blendermcp_use_ambientcg:
            info = col.row()
            info.label(text=t("info_ambientcg_assets"), icon="INFO")

        layout.separator(factor=0.3)

        # Sketchfab
        col = layout.column(align=True)
        col.prop(scene, "blendermcp_use_sketchfab", text=t("prop_sketchfab_assets"), icon="MESH_MONKEY")
        if scene.blendermcp_use_sketchfab:
            col.prop(scene, "blendermcp_sketchfab_api_key", text=t("prop_api_key"))
            warn = col.row()
            warn.alert = True
            warn.label(text=t("warn_api_key_saved"), icon="ERROR")

        layout.separator(factor=0.3)

        # Code Execution
        col = layout.column(align=True)
        col.prop(scene, "blendermcp_allow_code_execution", text=t("prop_remote_code"), icon="SCRIPT")
        if scene.blendermcp_allow_code_execution:
            warn = col.row()
            warn.alert = True
            warn.label(text=t("warn_remote_code"), icon="ERROR")


# =============================================================================
# Sub-Panel: Client Setup (first-time configuration)
# =============================================================================
class BLENDERMCP_PT_ClientSetup(bpy.types.Panel):
    bl_label = t("panel_client_setup_label")
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
        layout.label(text=t("step_choose_client"), icon="QUESTION")
        layout.prop(scene, "blendermcp_client_target", text="")

        layout.separator(factor=0.3)

        # Step 2: Copy config
        layout.label(text=t("step_copy_config"), icon="COPYDOWN")
        layout.operator(
            "blendermcp.copy_mcp_client_config",
            text=t("btn_copy_config"),
            icon="COPYDOWN",
        )

        layout.separator(factor=0.3)

        # Step 3: Run server
        layout.label(text=t("step_run_server"), icon="PLAY")
        layout.operator(
            "blendermcp.run_mcp_terminal_server",
            text=t("btn_run_server"),
            icon="CONSOLE",
        )


# =============================================================================
# Sub-Panel: Tools (diagnostics, logs, deps)
# =============================================================================
class BLENDERMCP_PT_Tools(bpy.types.Panel):
    bl_label = t("panel_tools_label")
    bl_idname = "BLENDERMCP_PT_Tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BlenderMCP"
    bl_parent_id = "BLENDERMCP_PT_Panel"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout

        col = layout.column(align=True)
        col.operator("blendermcp.install_dependencies", text=t("btn_install_deps"), icon="IMPORT")
        col.operator("blendermcp.health_check", text=t("btn_health_check"), icon="CHECKMARK")
        col.operator("blendermcp.open_logs", text=t("btn_open_logs"), icon="TEXT")


# =============================================================================
# Sub-Panel: Status & Cache (last action + asset info)
# =============================================================================
class BLENDERMCP_PT_StatusAndCache(bpy.types.Panel):
    bl_label = t("panel_status_cache_label")
    bl_idname = "BLENDERMCP_PT_StatusAndCache"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BlenderMCP"
    bl_parent_id = "BLENDERMCP_PT_Panel"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # --- Section 1: Last Action ---
        box = layout.box()
        box.label(text=t("label_last_action"), icon="INFO")
        
        if scene.blendermcp_last_action:
            icon = "CHECKMARK" if scene.blendermcp_last_action_ok else "ERROR"
            row = box.row()
            row.alert = not scene.blendermcp_last_action_ok
            row.label(text=scene.blendermcp_last_action, icon=icon)
            
            row = box.row()
            row.label(text=scene.blendermcp_last_action_at, icon="TIME")
            
            if scene.blendermcp_last_action_details:
                # Wrap long details
                row = box.row()
                row.label(text=scene.blendermcp_last_action_details[:60])
        else:
            box.label(text=t("label_no_actions"), icon="DOT")

        layout.separator(factor=0.5)

        # --- Section 2: Asset Cache ---
        box = layout.box()
        box.label(text=t("label_asset_cache"), icon="FILE_CACHE")
        
        try:
            addon_mod = _get_addon_module()
            cache_size, file_count = addon_mod._asset_cache.get_cache_size()
        except Exception:
            cache_size, file_count = 0, 0

        size_mb = cache_size / (1024 * 1024)
        
        row = box.row(align=True)
        row.label(text=t("label_cache_info", count=file_count, size=size_mb))
        
        row = box.row()
        row.scale_y = 1.2
        row.operator("blendermcp.clear_cache", text=t("btn_clear_cache"), icon="TRASH")


# All panel classes in registration order (parent first, then children)
PANEL_CLASSES = [
    BLENDERMCP_PT_Panel,
    BLENDERMCP_PT_Integrations,
    BLENDERMCP_PT_ClientSetup,
    BLENDERMCP_PT_Tools,
    BLENDERMCP_PT_StatusAndCache,
]
