"""BlenderMCP UI Panel - redesigned with collapsible sub-panels for better UX."""

import os
import sys

import bpy
import importlib.util as _iu


def _get_addon_module():
    """Load the main addon module safely in all Blender loading modes."""
    # 1. Try via package if available (standard Extension mode)
    if __package__:
        parts = __package__.split('.')
        try:
            # We look for the root module in sys.modules by going up the namespace levels.
            # In Blender Extensions, this is typically bl_ext.<repo>.<extension_id>
            # In legacy addons, it is just <addon_id>
            for i in range(len(parts), 0, -1):
                root_maybe = ".".join(parts[:i])
                if root_maybe in sys.modules:
                    mod = sys.modules[root_maybe]
                    if hasattr(mod, "BlenderMCPServer"):
                        return mod
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
# Main Panel: Connection & Status
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

        # --- Connection Status ---
        if scene.blendermcp_server_running:
            status_row = layout.row()
            status_row.label(text=t("status_connected", port=scene.blendermcp_port), icon="CHECKMARK")
            layout.operator("blendermcp.stop_server", text=t("btn_disconnect"), icon="CANCEL")
        else:
            status_row = layout.row()
            status_row.alert = True
            status_row.label(text=t("status_disconnected"), icon="ERROR")
            
            row = layout.row(align=True)
            row.scale_y = 1.4
            row.operator("blendermcp.start_server", text=t("btn_connect"), icon="PLAY")

        layout.separator(factor=0.5)
        
        # --- Last Action Summary (Previously separate Status & Cache) ---
        if scene.blendermcp_last_action:
            box = layout.box()
            row = box.row()
            icon = "CHECKMARK" if scene.blendermcp_last_action_ok else "ERROR"
            row.alert = not scene.blendermcp_last_action_ok
            row.label(text=f"{scene.blendermcp_last_action}: {scene.blendermcp_last_action_details[:30]}...", icon=icon)


# =============================================================================
# Sub-Panel: 3D Printing & Engineering
# =============================================================================
class BLENDERMCP_PT_Engineering(bpy.types.Panel):
    bl_label = t("panel_engineering_label")
    bl_idname = "BLENDERMCP_PT_Engineering"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BlenderMCP"
    bl_parent_id = "BLENDERMCP_PT_Panel"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # Mesh Cleanup
        col = layout.column(align=True)
        col.label(text=t("label_mesh_cleanup"))
        col.operator("blendermcp.auto_repair_mesh", text=t("btn_auto_repair"), icon="MODIFIER")
        col.operator("blendermcp.resolve_self_intersections", text=t("btn_resolve_intersections"), icon="MOD_BOOLEAN")
        
        layout.separator(factor=0.5)

        # Functional Management
        col = layout.column(align=True)
        col.label(text=t("label_functional_mgmt"))
        col.operator("blendermcp.mark_functional_part", text=t("btn_mark_part"), icon="PROPERTIES")


# =============================================================================
# Sub-Panel: Integrations (Poly Haven, Sketchfab, etc.)
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

        col = layout.column(align=True)
        col.label(text=t("label_external_assets"))
        
        # Poly Haven
        row = col.row(align=True)
        row.prop(scene, "blendermcp_use_polyhaven", text=t("prop_polyhaven_assets"), icon="WORLD")
        
        # AmbientCG
        row = col.row(align=True)
        row.prop(scene, "blendermcp_use_ambientcg", text=t("prop_ambientcg_assets"), icon="MATERIAL")

        # Sketchfab
        row = col.row(align=True)
        row.prop(scene, "blendermcp_use_sketchfab", text=t("prop_sketchfab_assets"), icon="MESH_MONKEY")
        
        if scene.blendermcp_use_sketchfab:
            box = layout.box()
            box.prop(scene, "blendermcp_sketchfab_api_key", text=t("prop_api_key"))
            
            op = box.operator("blendermcp.open_url", text=t("btn_get_api_key"), icon="URL")
            op.url = "https://sketchfab.com/settings/password"
            
            warn = box.row()
            warn.alert = True
            warn.label(text=t("warn_api_key_saved"), icon="ERROR")

        # BlenderKit
        row = col.row(align=True)
        row.prop(scene, "blendermcp_use_blenderkit", text="BlenderKit Assets", icon="IMAGE_DATA")
        
        if scene.blendermcp_use_blenderkit:
            box = layout.box()
            box.prop(scene, "blendermcp_blenderkit_api_key", text=t("prop_api_key"))
            
            op = box.operator("blendermcp.open_url", text=t("btn_get_token_bk"), icon="URL")
            op.url = "https://www.blenderkit.com/settings/profile/"
            
            warn = box.row()
            warn.alert = True
            warn.label(text=t("warn_api_key_saved"), icon="ERROR")


# =============================================================================
# Sub-Panel: Online AI Assistant (New)
# =============================================================================
class BLENDERMCP_PT_OnlineLLM(bpy.types.Panel):
    bl_label = t("label_llm_assistant")
    bl_idname = "BLENDERMCP_PT_OnlineLLM"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BlenderMCP"
    bl_parent_id = "BLENDERMCP_PT_Panel"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        col = layout.column(align=True)
        col.prop(scene, "blendermcp_llm_provider", text=t("label_llm_provider"))
        
        provider = scene.blendermcp_llm_provider
        
        box = layout.box()
        if provider == "OPENAI":
            box.prop(scene, "blendermcp_openai_key", text="OpenAI Key")
            box.prop(scene, "blendermcp_openai_model", text=t("label_llm_model"))
            op = box.operator("blendermcp.open_url", text=t("btn_get_openai_key"), icon="URL")
            op.url = "https://platform.openai.com/api-keys"
        elif provider == "ANTHROPIC":
            box.prop(scene, "blendermcp_anthropic_key", text="Claude Key")
            box.prop(scene, "blendermcp_anthropic_model", text=t("label_llm_model"))
            op = box.operator("blendermcp.open_url", text=t("btn_get_anthropic_key"), icon="URL")
            op.url = "https://console.anthropic.com/settings/keys"
        elif provider == "GOOGLE":
            box.prop(scene, "blendermcp_google_key", text="Gemini Key")
            box.prop(scene, "blendermcp_google_model", text=t("label_llm_model"))
            op = box.operator("blendermcp.open_url", text=t("btn_get_google_key"), icon="URL")
            op.url = "https://aistudio.google.com/app/apikey"

        layout.separator()
        
        # Chat interface
        chat_box = layout.box()
        chat_box.label(text=t("label_chat_with_ai"), icon="CONSOLE")
        chat_box.prop(scene, "blendermcp_chat_prompt", text="")
        
        row = chat_box.row(align=True)
        row.operator("blendermcp.send_chat", text=t("btn_send_prompt"), icon="PLAY")
        row.operator("blendermcp.clear_chat", text="", icon="X")
        
        if scene.blendermcp_chat_status:
            status_box = chat_box.box()
            status_box.label(text=t("status_ai_label"))
            status_col = status_box.column()
            status_col.scale_y = 0.8
            # Split status by lines if it's long
            lines = scene.blendermcp_chat_status.split("\n")
            for line in lines[:5]: # Show first 5 lines
                status_col.label(text=line)
            if len(lines) > 5:
                status_col.label(text="...")




# =============================================================================
# Sub-Panel: Setup & Maintenance (Consolidated)
# =============================================================================
class BLENDERMCP_PT_Setup(bpy.types.Panel):
    bl_label = t("panel_setup_maint_label")
    bl_idname = "BLENDERMCP_PT_Setup"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BlenderMCP"
    bl_parent_id = "BLENDERMCP_PT_Panel"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # Main Setup
        col = layout.column(align=True)
        col.operator("blendermcp.install_dependencies", text=t("btn_install_deps"), icon="IMPORT")
        col.operator("blendermcp.health_check", text=t("btn_health_check"), icon="CHECKMARK")
        
        layout.separator(factor=0.5)

        # Integrations (Security side)
        layout.prop(scene, "blendermcp_allow_code_execution", text=t("label_remote_code_short"), icon="SCRIPT")
        
        layout.separator(factor=0.5)
        
        # Advanced Toggle
        layout.prop(scene, "blendermcp_show_advanced", icon="SETTINGS", toggle=True)
        
        if scene.blendermcp_show_advanced:
            box = layout.box()
            box.label(text=t("label_advanced_section"), icon="CONSOLE")
            box.prop(scene, "blendermcp_client_target")
            box.operator("blendermcp.copy_mcp_client_config")
            box.operator("blendermcp.run_mcp_terminal_server")
            box.separator()
            box.operator("blendermcp.open_logs", icon="TEXT")
            box.operator("blendermcp.clear_cache", icon="TRASH")


# All panel classes in registration order
PANEL_CLASSES = [
    BLENDERMCP_PT_Panel,
    BLENDERMCP_PT_Engineering,
    BLENDERMCP_PT_Integrations,
    BLENDERMCP_PT_OnlineLLM,
    BLENDERMCP_PT_Setup,
]
