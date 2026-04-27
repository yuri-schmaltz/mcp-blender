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
            # Check if already loaded by Blender (including extension naming)
            for name, mod in sys.modules.items():
                if hasattr(mod, "__file__") and mod.__file__ and os.path.abspath(mod.__file__) == os.path.abspath(addon_py):
                    return mod
                if "addon_entry" in name and hasattr(mod, "BlenderMCPServer"):
                    return mod
            
            # Load dynamic spec if not already in sys.modules
            spec = _iu.spec_from_file_location("_blendermcp_addon_ref_panel", addon_py)
            mod = _iu.module_from_spec(spec)
            # Propagate root package if possible
            if __package__:
                parts = __package__.split('.')
                if len(parts) >= 3:
                    mod.__package__ = ".".join(parts[:3])
                else:
                    mod.__package__ = parts[0]
            spec.loader.exec_module(mod)
            return mod
            
    raise ImportError("Could not locate BlenderMCP main module (addon.py or __init__.py)")

# Import i18n
_i18n_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "utils", "i18n.py")
_i18n_spec = _iu.spec_from_file_location("_blendermcp_i18n_panel", _i18n_path)
_i18n = _iu.module_from_spec(_i18n_spec)
_i18n_spec.loader.exec_module(_i18n)
t = _i18n.t


def get_prefs(context):
    """Access global addon preferences safely."""
    pkg = __package__
    if pkg and pkg.startswith("bl_ext."):
        # Extension mode: bl_ext.user_default.mcp_blender.addon.ui -> bl_ext.user_default.mcp_blender
        parts = pkg.split(".")
        root_pkg = ".".join(parts[:3]) if len(parts) >= 3 else pkg
    elif pkg:
        root_pkg = pkg.split(".")[0]
    else:
        root_pkg = "mcp_blender"
    
    if root_pkg in context.preferences.addons:
        return context.preferences.addons[root_pkg].preferences
    return None


# =============================================================================
# Main Panel: Connection & Status
# =============================================================================
class BLENDERMCP_PT_Panel(bpy.types.Panel):
    bl_label = "Blender MCP"
    bl_idname = "BLENDERMCP_PT_Panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MCP"

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
    bl_category = "MCP"
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

        # Functional Part Management
        col = layout.column(align=True)
        col.label(text=t("label_functional_mgmt"))
        
        # Preset & Role selectors
        row = col.row(align=True)
        row.prop(scene, "blendermcp_part_preset", text="")
        row = col.row(align=True)
        row.prop(scene, "blendermcp_part_role", text="")
        
        col.operator("blendermcp.mark_functional_part", text=t("btn_mark_part"), icon="PROPERTIES")
        
        # Show current part info on active object
        obj = context.active_object
        if obj and obj.get("mcp_functional_part"):
            info_box = layout.box()
            info_box.scale_y = 0.85
            preset_tag = obj.get("mcp_part_preset", "?")
            role_tag = obj.get("mcp_part_role", "?")
            info_box.label(text=f"{obj.name}  →  {preset_tag} / {role_tag}", icon="CHECKMARK")


# =============================================================================
# Sub-Panel: Integrations (Poly Haven, Sketchfab, etc.)
# =============================================================================
class BLENDERMCP_PT_Integrations(bpy.types.Panel):
    bl_label = t("panel_integrations_label")
    bl_idname = "BLENDERMCP_PT_Integrations"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MCP"
    bl_parent_id = "BLENDERMCP_PT_Panel"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        prefs = get_prefs(context)
        if not prefs:
            layout.label(text="Preferences not found", icon="ERROR")
            return

        col = layout.column(align=True)
        col.label(text="Manage all integrations and API keys in the Addon Preferences.")
        
        layout.separator()
        # Open local Preferences
        layout.operator("screen.userpref_show", text="Open Addon Settings", icon="PREFERENCES")


# =============================================================================
# Sub-Panel: Setup & Maintenance (Consolidated)
# =============================================================================
class BLENDERMCP_PT_Setup(bpy.types.Panel):
    bl_label = t("panel_setup_maint_label")
    bl_idname = "BLENDERMCP_PT_Setup"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MCP"
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
        prefs = get_prefs(context)
        if prefs:
            layout.prop(prefs, "allow_code_execution", text=t("label_remote_code_short"), icon="SCRIPT")
        else:
            layout.label(text="Preferences not found", icon="ERROR")
        
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
    BLENDERMCP_PT_Setup,
]
