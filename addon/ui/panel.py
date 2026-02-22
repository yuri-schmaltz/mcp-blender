"""BlenderMCP UI Panel - extracted from addon.py for modularity."""

import bpy


class BLENDERMCP_PT_Panel(bpy.types.Panel):
    bl_label = "Blender MCP"
    bl_idname = "BLENDERMCP_PT_Panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BlenderMCP"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        if not scene.blendermcp_server_running:
            setup_box = layout.box()
            setup_box.label(text="Connection Configuration:", icon="OPTIONS")
            setup_box.prop(scene, "blendermcp_port")
            setup_box.prop(scene, "blendermcp_use_polyhaven", text="Use assets from Poly Haven")

            if scene.blendermcp_use_polyhaven:
                setup_box.label(text="Powered by Polyhaven API. We are not affiliated with them", icon="INFO")

            setup_box.prop(scene, "blendermcp_use_sketchfab", text="Use assets from Sketchfab")
            if scene.blendermcp_use_sketchfab:
                setup_box.label(
                    text="Need to provide API Key to use Sketchfab. Powered by Sketchfab API",
                    icon="INFO",
                )
                setup_box.prop(scene, "blendermcp_sketchfab_api_key", text="API Key")

            setup_box.separator()
            setup_box.prop(scene, "blendermcp_allow_code_execution", text="Allow Remote Code Execution", icon="ERROR")
            if scene.blendermcp_allow_code_execution:
                row = setup_box.row()
                row.alert = True
                row.label(text="Warning: allows LLM to run arbitrary Python code.", icon="ERROR")

            layout.operator("blendermcp.start_server", text="Connect to LLM client", icon="PLAY")
        else:
            layout.operator("blendermcp.stop_server", text="Disconnect", icon="CANCEL")
            layout.label(text=f"Running on port {scene.blendermcp_port}")

        setup_box = layout.box()
        setup_box.label(text="Local Setup", icon="CONSOLE")
        setup_box.operator(
            "blendermcp.install_dependencies",
            text="Check/Install Dependencies",
            icon="IMPORT",
        )
        setup_box.operator(
            "blendermcp.run_mcp_terminal_server",
            text="Run MCP Server in Terminal",
            icon="PLAY",
        )
        setup_box.prop(scene, "blendermcp_client_target", text="Client")
        setup_box.operator(
            "blendermcp.copy_mcp_client_config",
            text="Copy MCP Client Config",
            icon="COPYDOWN",
        )
        setup_box.operator(
            "blendermcp.health_check",
            text="Health Check",
            icon="CHECKMARK",
        )
        setup_box.operator(
            "blendermcp.open_logs",
            text="Open Logs",
            icon="TEXT",
        )

        status_box = layout.box()
        status_box.label(text="Last Action", icon="INFO")
        if scene.blendermcp_last_action:
            status = "OK" if scene.blendermcp_last_action_ok else "ERROR"
            status_box.label(text=f"{status}: {scene.blendermcp_last_action}")
            status_box.label(text=f"When: {scene.blendermcp_last_action_at}")
            if scene.blendermcp_last_action_details:
                status_box.label(text=scene.blendermcp_last_action_details[:80])
        else:
            status_box.label(text="No action recorded yet.")

        # MP-05: Asset cache management
        layout.separator()
        cache_box = layout.box()
        cache_box.label(text="Asset Cache", icon="FILE_CACHE")

        # Lazy import to get asset cache instance
        import importlib
        try:
            addon_mod = importlib.import_module("addon")
            cache_size, file_count = addon_mod._asset_cache.get_cache_size()
        except Exception:
            cache_size, file_count = 0, 0

        size_mb = cache_size / (1024 * 1024)
        cache_box.label(text=f"Files: {file_count}, Size: {size_mb:.1f} MB")
        cache_box.operator("blendermcp.clear_cache", text="Clear Cache", icon="TRASH")

    @staticmethod
    def _draw_api_key_warning(layout):
        """Draw security warning box for API keys."""
        box = layout.box()
        box.alert = True
        box.label(text="⚠️ API keys are saved in .blend file", icon="ERROR")
        box.label(text="Do not share this file publicly", icon="BLANK1")


PANEL_CLASSES = [BLENDERMCP_PT_Panel]
