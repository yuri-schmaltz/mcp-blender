"""BlenderMCP UI Panel - redesigned with collapsible sub-panels for better UX."""

import importlib.util as _iu
import sys

import bpy


def _get_addon_module():
    """Load the main addon module safely using package context."""
    if __package__:
        # bl_ext.user_default.mcp_blender.addon.ui -> bl_ext.user_default.mcp_blender.addon_entry
        pkg_root = ".".join(__package__.split(".")[:3])
        entry_name = f"{pkg_root}.addon_entry"
        if entry_name in sys.modules:
            return sys.modules[entry_name]

    # Fallback to searching in sys.modules
    for name, mod in sys.modules.items():
        if name.endswith(".addon_entry") and hasattr(mod, "BlenderMCPServer"):
            return mod
    return None


# Import i18n
from ..utils import i18n

t = i18n.t


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
        if layout is None:
            return
        scene = context.scene

        # --- Connection Status ---
        if scene.blendermcp_server_running:
            status_row = layout.row()
            status_row.label(
                text=t("status_connected", port=scene.blendermcp_port), icon="CHECKMARK"
            )
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
            row.label(
                text=f"{scene.blendermcp_last_action}: {scene.blendermcp_last_action_details[:30]}...",
                icon=icon,
            )


# =============================================================================
# Sub-Panel: Chat & AI Command Prompt
# =============================================================================
class BLENDERMCP_PT_Chat(bpy.types.Panel):
    bl_label = "Built-in AI Chat"
    bl_idname = "BLENDERMCP_PT_Chat"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MCP"
    bl_parent_id = "BLENDERMCP_PT_Panel"

    def draw(self, context):
        layout = self.layout
        if layout is None:
            return
        scene = context.scene
        prefs = get_prefs(context)

        # Check if litellm is installed
        litellm_installed = False
        try:
            if _iu.find_spec("litellm") is not None:
                litellm_installed = True
            else:
                from ..utils.helpers import extend_sys_path_with_venv

                extend_sys_path_with_venv()
                if _iu.find_spec("litellm") is not None:
                    litellm_installed = True
        except Exception:
            pass

        if not litellm_installed:
            box = layout.box()
            box.alert = True
            box.label(text="AI Chat: litellm is not installed.", icon="ERROR")
            box.operator(
                "blendermcp.install_dependencies", text="Install Dependencies", icon="IMPORT"
            )
            return

        col = layout.column(align=True)
        col.label(text="Command Prompt:")

        # We use a large string property if we want multi-line,
        # but standard string property is limited.
        # For multiline, we just use layout.prop with text=""
        row = col.row()
        row.scale_y = 1.5
        row.prop(scene, "blendermcp_chat_prompt", text="")

        row = col.row(align=True)
        row.scale_y = 1.2
        row.operator("blendermcp.send_chat", text="Send to AI", icon="PLAY")
        row.operator("blendermcp.clear_chat", text="", icon="TRASH")

        if scene.blendermcp_chat_status:
            box = layout.box()
            box.label(text=scene.blendermcp_chat_status, icon="INFO")

        layout.separator()

        col = layout.column(align=True)
        if (
            getattr(bpy.types, "blendermcp_webui_server", None)
            and bpy.types.blendermcp_webui_server.server
        ):
            col.operator("blendermcp.stop_webui", text="Stop WebUI Server", icon="CANCEL")

            # Open WebUI URL
            op = col.operator("blendermcp.open_url", text="Open WebUI in Browser", icon="URL")
            op.target_url = f"http://localhost:{prefs.webui_port}"
        else:
            col.operator("blendermcp.start_webui", text="Start WebUI Server", icon="WORLD_DATA")


# All panel classes in registration order
PANEL_CLASSES = [
    BLENDERMCP_PT_Panel,
    BLENDERMCP_PT_Chat,
]
