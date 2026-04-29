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
_i18n_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "utils", "i18n.py")
_i18n_spec = _iu.spec_from_file_location("_blendermcp_i18n_operators", _i18n_path)
_i18n = _iu.module_from_spec(_i18n_spec)
_i18n_spec.loader.exec_module(_i18n)
t = _i18n.t

# Import handlers directly to avoid legacy _call_handler
from ..handlers import mesh_tools, functional_parts


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
    # addon/ui/operators.py -> addon/ui -> addon -> project_root
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
            spec = _iu.spec_from_file_location("blender_mcp_addon_ui_core", addon_py)
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
        client = scene.blendermcp_client_target
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
# Operator: Resolve Self-Intersections
# ---------------------------------------------------------------------------
class BLENDERMCP_OT_ResolveSelfIntersections(bpy.types.Operator):
    bl_idname = "blendermcp.resolve_self_intersections"
    bl_label = "Resolve Self-Intersections"
    bl_description = "Merge internal overlapping shells while preserving shape"

    def execute(self, context):
        from ..handlers import mesh_tools
        if not context.active_object or context.active_object.type != 'MESH':
            self.report({"ERROR"}, "Select a mesh first")
            return {"CANCELLED"}
        
        # Use direct import instead of legacy _call_handler
        result = mesh_tools.resolve_self_intersections(bpy.context.scene, context.active_object.name)
        
        if "error" in result:
            self.report({"ERROR"}, result["error"])
            _update_action_status(context.scene, "Resolve Intersections", False, result["error"])
            return {"CANCELLED"}
            
        self.report({"INFO"}, result["message"])
        _update_action_status(context.scene, "Resolve Intersections", True, result["message"])
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Operator: Mark as Functional Part
# ---------------------------------------------------------------------------
class BLENDERMCP_OT_MarkFunctionalPart(bpy.types.Operator):
    bl_idname = "blendermcp.mark_functional_part"
    bl_label = "Mark as Functional Part"
    bl_description = "Tag the active object with a role from the selected preset"

    def execute(self, context):
        from ..handlers import functional_parts
        if not context.active_object:
            self.report({"ERROR"}, "No active object")
            return {"CANCELLED"}
        
        scene = context.scene
        preset = scene.blendermcp_part_preset
        role = scene.blendermcp_part_role
        
        # Use direct import instead of legacy _call_handler
        result = functional_parts.mark_as_functional_part(
            bpy.context.scene, context.active_object.name,
            role=role, preset=preset,
        )
        
        if "error" in result:
            self.report({"ERROR"}, result["error"])
            return {"CANCELLED"}
            
        self.report({"INFO"}, result["message"])
        _update_action_status(scene, "Mark Part", True, result["message"])
        return {"FINISHED"}


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

        
        # Use a brief timer to allow UI update before blocking request
        # Actually, in Blender, we can't easily do async without threading
        # For now, we'll do it synchronously for simplicity
        
        from ..handlers import llm_handler  # type: ignore

        result = llm_handler.handle_chat_request(context)
        
        if "error" in result:
            self.report({"ERROR"}, result["error"])
            scene.blendermcp_chat_status = f"Error: {result['error']}"
            _update_action_status(scene, "AI Chat", False, result["error"])
        else:
            status = result.get("status", "success")
            msg = result.get("message", "Done")
            scene.blendermcp_chat_status = msg
            
            if status == "success":
                self.report({"INFO"}, "AI execution completed.")
                _update_action_status(scene, "AI Chat", True, "Execution success")
            elif status == "pending":
                self.report({"WARNING"}, "Code generated (Execution disabled)")
                _update_action_status(scene, "AI Chat", True, "Code generated")
            else:
                self.report({"INFO"}, "AI response received.")
                _update_action_status(scene, "AI Chat", True, "Response received")
                
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
    BLENDERMCP_OT_ResolveSelfIntersections,
    BLENDERMCP_OT_MarkFunctionalPart,
    BLENDERMCP_OT_OpenURL,
    BLENDERMCP_OT_SendChat,
    BLENDERMCP_OT_ClearChat,
]

