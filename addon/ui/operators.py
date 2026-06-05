"""BlenderMCP UI Operators - extracted from addon.py for modularity."""

import os
import subprocess
import sys

import bpy  # type: ignore

# Load helpers via filesystem to work in both repo and Blender extension mode.
import importlib.util as _iu

_helpers_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "utils", "helpers.py")
_helpers_spec = _iu.spec_from_file_location("_blendermcp_addon_helpers", _helpers_path)
_helpers = _iu.module_from_spec(_helpers_spec)
if __package__:
   _helpers.__package__ = __package__
_helpers_spec.loader.exec_module(_helpers)

_project_root = _helpers._project_root
_run_command = _helpers._run_command
_resolve_uv_command = _helpers._resolve_uv_command
_uv_blender_mcp_command = _helpers._uv_blender_mcp_command
_install_runtime_dependencies_with_pip = _helpers._install_runtime_dependencies_with_pip
_mcp_client_config_snippet = _helpers._mcp_client_config_snippet
_update_action_status = _helpers._update_action_status
_logs_path = _helpers._logs_path
_open_in_system = _helpers._open_in_system

# Import i18n
from ..utils import i18n
t = i18n.t

# Import handlers directly to avoid legacy _call_handler
from ..handlers import mesh_tools, functional_parts


def _get_addon_module():
    """Load the main addon module safely using package context."""
    if __package__:
        # bl_ext.user_default.mcp_blender.addon.ui -> bl_ext.user_default.mcp_blender.addon_entry
        pkg_root = ".".join(__package__.split('.')[:3])
        entry_name = f"{pkg_root}.addon_entry"
        if entry_name in sys.modules:
            return sys.modules[entry_name]
    
    # Fallback to searching in sys.modules
    for name, mod in sys.modules.items():
        if name.endswith(".addon_entry") and hasattr(mod, "BlenderMCPServer"):
            return mod
    return None


# ---------------------------------------------------------------------------
# Operator: Start Server
# ---------------------------------------------------------------------------
class BLENDERMCP_OT_StartServer(bpy.types.Operator):
    bl_idname = "blendermcp.start_server"
    bl_label = t("op_start_server_label")
    bl_description = t("op_start_server_desc")

    def execute(self, context):
        addon_mod = _get_addon_module()
        server_cls = addon_mod.BlenderMCPServer

        scene = context.scene
        if not hasattr(bpy.types, "blendermcp_server") or not bpy.types.blendermcp_server:
            bpy.types.blendermcp_server = server_cls(port=scene.blendermcp_port)

        bpy.types.blendermcp_server.start()
        scene.blendermcp_server_running = True
        _update_action_status(scene, t("btn_connect"), True, t("msg_server_listening", port=scene.blendermcp_port))
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Operator: Install Dependencies
# ---------------------------------------------------------------------------
class BLENDERMCP_OT_InstallDependencies(bpy.types.Operator):
    bl_idname = "blendermcp.install_dependencies"
    bl_label = "Check/Install Dependencies"
    bl_description = "Install dependencies via uv sync (repo) or pip fallback (installed addon)"

    def execute(self, context):
        root = _project_root()
        pyproject_path = os.path.join(root, "pyproject.toml")

        if os.path.exists(pyproject_path):
            uv_prefix = _resolve_uv_command(root)
            if uv_prefix is None:
                self.report(
                    {"ERROR"},
                    "uv not found. Install uv or run from a shell where uv is available.",
                )
                _update_action_status(context.scene, "Check/Install Dependencies", False, "uv not found")
                return {"CANCELLED"}

            code, output = _run_command(
                [*uv_prefix, "sync", "--extra", "gui", "--extra", "test"],
                cwd=root,
            )
            if code != 0:
                self.report({"ERROR"}, "Dependency sync failed. See Blender console for details.")
                if output:
                    print("[blender-mcp] uv sync output:")
                    print(output)
                _update_action_status(context.scene, "Check/Install Dependencies", False, "uv sync failed")
                return {"CANCELLED"}

            self.report({"INFO"}, t("msg_dependencies_ready"))
            _update_action_status(context.scene, t("btn_install_deps"), True, "uv sync completed")
            return {"FINISHED"}

        code, output = _install_runtime_dependencies_with_pip(root)
        if code != 0:
            self.report({"ERROR"}, "Fallback install failed. See Blender console for details.")
            if output:
                print("[blender-mcp] pip install output:")
                print(output)
            _update_action_status(context.scene, "Check/Install Dependencies", False, "pip fallback failed")
            return {"CANCELLED"}

        self.report({"INFO"}, t("msg_dependencies_installed_pip"))
        _update_action_status(context.scene, t("btn_install_deps"), True, "pip fallback completed")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Operator: Run MCP Server Terminal
# ---------------------------------------------------------------------------
class BLENDERMCP_OT_RunMCPServerTerminal(bpy.types.Operator):
    bl_idname = "blendermcp.run_mcp_terminal_server"
    bl_label = t("btn_run_server")
    bl_description = "Launch uv run blender-mcp --host localhost --port <port> in a new terminal"

    def execute(self, context):
        port = int(context.scene.blendermcp_port)
        root = _project_root()
        host = "localhost"
        cmd = _uv_blender_mcp_command(root, host=host, port=port, doctor=False)
        if cmd is None:
            self.report({"ERROR"}, "uv not found. Install uv first.")
            _update_action_status(context.scene, "Run MCP Server in Terminal", False, "uv not found")
            return {"CANCELLED"}

        try:
            if os.name == "nt":
                subprocess.Popen(
                    cmd,
                    cwd=root,
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
            else:
                subprocess.Popen(cmd, cwd=root)
        except Exception as exc:
            self.report({"ERROR"}, f"Failed to start MCP server terminal: {exc}")
            _update_action_status(context.scene, "Run MCP Server in Terminal", False, str(exc))
            return {"CANCELLED"}

        self.report({"INFO"}, t("msg_server_launched", host=host, port=port))
        _update_action_status(context.scene, t("btn_run_server"), True, f"Started on {host}:{port}")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Operator: Copy MCP Client Config
# ---------------------------------------------------------------------------
class BLENDERMCP_OT_CopyMCPClientConfig(bpy.types.Operator):
    bl_idname = "blendermcp.copy_mcp_client_config"
    bl_label = t("btn_copy_config")
    bl_description = "Copy stdio config snippet for Claude/Cursor/Ollama/LM Studio"

    def execute(self, context):
        scene = context.scene
        from .panel import get_prefs
        prefs = get_prefs(context)
        client = prefs.client_target if prefs else 'lm_studio'
        snippet = _mcp_client_config_snippet(client, host="localhost", port=int(scene.blendermcp_port))
        context.window_manager.clipboard = snippet
        self.report({"INFO"}, t("msg_copied_config", client=client))
        _update_action_status(scene, t("btn_copy_config"), True, f"Client: {client}")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Operator: Health Check
# ---------------------------------------------------------------------------
class BLENDERMCP_OT_HealthCheck(bpy.types.Operator):
    bl_idname = "blendermcp.health_check"
    bl_label = t("btn_health_check")
    bl_description = "Run local diagnostics (uv + blender-mcp --doctor)"

    def execute(self, context):
        root = _project_root()
        port = int(context.scene.blendermcp_port)
        cmd = _uv_blender_mcp_command(root, host="localhost", port=port, doctor=True)
        if cmd is None:
            self.report({"ERROR"}, "uv not found in PATH.")
            _update_action_status(context.scene, "Health Check", False, "uv not found")
            return {"CANCELLED"}

        code, output = _run_command(cmd, cwd=root)
        if output:
            print("[blender-mcp] doctor output:")
            print(output)
        if code != 0:
            self.report({"ERROR"}, "Health check failed. See Blender console.")
            _update_action_status(context.scene, "Health Check", False, "doctor failed")
            return {"CANCELLED"}

        self.report({"INFO"}, t("msg_health_check_passed"))
        _update_action_status(context.scene, t("btn_health_check"), True, f"doctor ok for localhost:{port}")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Operator: Open Logs
# ---------------------------------------------------------------------------
class BLENDERMCP_OT_OpenLogs(bpy.types.Operator):
    bl_idname = "blendermcp.open_logs"
    bl_label = t("btn_open_logs")
    bl_description = "Open Blender MCP log file location"

    def execute(self, context):
        try:
            path = _logs_path()
            if not os.path.exists(path):
                open(path, "a", encoding="utf-8").close()
            _open_in_system(path)
        except Exception as exc:
            self.report({"ERROR"}, f"Could not open logs: {exc}")
            _update_action_status(context.scene, "Open Logs", False, str(exc))
            return {"CANCELLED"}

        self.report({"INFO"}, t("msg_opened_logs", path=path))
        _update_action_status(context.scene, t("btn_open_logs"), True, os.path.basename(path))
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Operator: Clear Cache (MP-05)
# ---------------------------------------------------------------------------
class BLENDERMCP_OT_ClearCache(bpy.types.Operator):
    bl_idname = "blendermcp.clear_cache"
    bl_label = t("btn_clear_cache")
    bl_description = "Clear all cached downloaded assets from Poly Haven and Sketchfab"

    def execute(self, context):
        addon_mod = _get_addon_module()
        deleted = addon_mod._asset_cache.clear()
        self.report({"INFO"}, t("msg_cleared_cache", count=deleted))
        _update_action_status(context.scene, t("btn_clear_cache"), True, f"Deleted files: {deleted}")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Operator: Stop Server
# ---------------------------------------------------------------------------
class BLENDERMCP_OT_StopServer(bpy.types.Operator):
    bl_idname = "blendermcp.stop_server"
    bl_label = t("op_stop_server_label")
    bl_description = t("op_stop_server_desc")

    def execute(self, context):
        scene = context.scene
        if hasattr(bpy.types, "blendermcp_server") and bpy.types.blendermcp_server:
            bpy.types.blendermcp_server.stop()
            del bpy.types.blendermcp_server
        scene.blendermcp_server_running = False
        _update_action_status(scene, "Disconnect from MCP server", True, "Server stopped")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Operator: Open URL
# ---------------------------------------------------------------------------
class BLENDERMCP_OT_OpenURL(bpy.types.Operator):
    bl_idname = "blendermcp.open_url"
    bl_label = "Open URL"
    bl_description = "Open a specific URL in the system browser"
    
    target_url: bpy.props.StringProperty(name="URL", default="")  # type: ignore


    def execute(self, context):
        if not self.target_url:
            return {"CANCELLED"}
        _open_in_system(self.target_url)
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Modal Operator: Download Progress (MP-02)
# ---------------------------------------------------------------------------
class BLENDERMCP_OT_DownloadProgress(bpy.types.Operator):
    """Display download progress with cancellation support."""

    bl_idname = "blendermcp.download_progress"
    bl_label = "Download Progress"

    operation_id: bpy.props.StringProperty(default="")  # type: ignore
    _timer = None
    _last_progress = 0

    def _get_progress_tracker(self):
        """Lazy load progress tracker from addon module."""
        try:
            addon_mod = _get_addon_module()
            if addon_mod.PROGRESS_AVAILABLE:
                return addon_mod.get_progress_tracker()
        except Exception:
            pass
        return None

    def modal(self, context, event):
        if event.type == "TIMER":
            tracker = self._get_progress_tracker()
            if tracker is None:
                self.cancel(context)
                return {"CANCELLED"}

            progress_info = tracker.get_progress(self.operation_id)
            if progress_info is None:
                self.cancel(context)
                return {"CANCELLED"}

            progress_pct = int(progress_info.progress_percent)
            if progress_pct != self._last_progress:
                context.window_manager.progress_update(progress_pct)
                self._last_progress = progress_pct

            if progress_info.status == "completed":
                context.window_manager.progress_end()
                self.report({"INFO"}, t("msg_download_complete", progress=progress_info.format_progress()))
                self.cancel(context)
                return {"FINISHED"}
            elif progress_info.status == "error":
                context.window_manager.progress_end()
                self.report({"ERROR"}, f"Download failed: {progress_info.error_message}")
                self.cancel(context)
                return {"CANCELLED"}
            elif progress_info.status == "cancelled":
                context.window_manager.progress_end()
                self.report({"WARNING"}, "Download cancelled by user")
                self.cancel(context)
                return {"CANCELLED"}

            context.area.tag_redraw() if hasattr(context, "area") and context.area else None

        elif event.type == "ESC":
            tracker = self._get_progress_tracker()
            if tracker:
                tracker.cancel_operation(self.operation_id)
            context.window_manager.progress_end()
            self.report({"WARNING"}, "Download cancelled (ESC pressed)")
            self.cancel(context)
            return {"CANCELLED"}

        return {"RUNNING_MODAL"}

    def execute(self, context):
        tracker = self._get_progress_tracker()
        if tracker is None:
            self.report({"ERROR"}, "Progress tracking not available")
            return {"CANCELLED"}

        if not self.operation_id:
            self.report({"ERROR"}, "No operation ID provided")
            return {"CANCELLED"}

        context.window_manager.progress_begin(0, 100)
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        if self._timer:
            wm = context.window_manager
            wm.event_timer_remove(self._timer)
            self._timer = None



# ---------------------------------------------------------------------------
# Operator: Send Chat (Online LLM)
# ---------------------------------------------------------------------------
class BLENDERMCP_OT_SendChat(bpy.types.Operator):
    bl_idname = "blendermcp.send_chat"
    bl_label = "Send to AI"
    bl_description = "Send prompt to selected online LLM provider"

    def execute(self, context):
        scene = context.scene
        scene.blendermcp_chat_status = t("status_ai_thinking")

        from ..handlers import llm_handler  # type: ignore

        def on_complete(result):
            if "error" in result:
                scene.blendermcp_chat_status = f"Error: {result['error']}"
                _update_action_status(scene, "AI Chat", False, result["error"])
            else:
                status = result.get("status", "success")
                msg = result.get("message", "Done")
                scene.blendermcp_chat_status = msg
                
                if status == "success":
                    _update_action_status(scene, "AI Chat", True, "Execution success")
                elif status == "pending":
                    _update_action_status(scene, "AI Chat", True, "Code generated")
                else:
                    _update_action_status(scene, "AI Chat", True, "Response received")
            
            # Force redraw of View3D areas to update panel labels instantly
            for screen in bpy.data.screens:
                for area in screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()

        llm_handler.handle_chat_request_async(context, on_complete)
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Operator: Clear Chat
# ---------------------------------------------------------------------------
class BLENDERMCP_OT_ClearChat(bpy.types.Operator):
    bl_idname = "blendermcp.clear_chat"
    bl_label = "Clear Chat"
    bl_description = "Clear prompt and status"

    def execute(self, context):
        scene = context.scene
        scene.blendermcp_chat_prompt = ""
        scene.blendermcp_chat_status = ""
        return {"FINISHED"}

# ---------------------------------------------------------------------------
# Operator: Start WebUI Server
# ---------------------------------------------------------------------------
class BLENDERMCP_OT_StartWebUI(bpy.types.Operator):
    bl_idname = "blendermcp.start_webui"
    bl_label = "Start WebUI Server"
    bl_description = "Start the embedded WebUI chat server in the background"

    def execute(self, context):
        scene = context.scene
        from .panel import get_prefs
        prefs = get_prefs(context)
        port = prefs.webui_port if prefs else 8080

        from ..webui_server import BlenderMCPWebUIServer

        if not hasattr(bpy.types, "blendermcp_webui_server") or not bpy.types.blendermcp_webui_server:
            bpy.types.blendermcp_webui_server = BlenderMCPWebUIServer(port=port)

        bpy.types.blendermcp_webui_server.port = port
        bpy.types.blendermcp_webui_server.start()
        
        self.report({"INFO"}, f"WebUI started on http://localhost:{port}")
        return {"FINISHED"}

# ---------------------------------------------------------------------------
# Operator: Stop WebUI Server
# ---------------------------------------------------------------------------
class BLENDERMCP_OT_StopWebUI(bpy.types.Operator):
    bl_idname = "blendermcp.stop_webui"
    bl_label = "Stop WebUI Server"
    bl_description = "Stop the embedded WebUI chat server"

    def execute(self, context):
        if hasattr(bpy.types, "blendermcp_webui_server") and bpy.types.blendermcp_webui_server:
            bpy.types.blendermcp_webui_server.stop()
            del bpy.types.blendermcp_webui_server
            
        self.report({"INFO"}, "WebUI stopped")
        return {"FINISHED"}



# All operator classes for registration
OPERATOR_CLASSES = [
    BLENDERMCP_OT_StartServer,
    BLENDERMCP_OT_StopServer,
    BLENDERMCP_OT_InstallDependencies,
    BLENDERMCP_OT_RunMCPServerTerminal,
    BLENDERMCP_OT_CopyMCPClientConfig,
    BLENDERMCP_OT_HealthCheck,
    BLENDERMCP_OT_OpenLogs,
    BLENDERMCP_OT_ClearCache,
    BLENDERMCP_OT_DownloadProgress,
    BLENDERMCP_OT_OpenURL,
    BLENDERMCP_OT_SendChat,
    BLENDERMCP_OT_ClearChat,
    BLENDERMCP_OT_StartWebUI,
    BLENDERMCP_OT_StopWebUI,
]

