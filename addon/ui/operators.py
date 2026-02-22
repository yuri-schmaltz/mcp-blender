"""BlenderMCP UI Operators - extracted from addon.py for modularity."""

import os
import subprocess

import bpy

from ..utils.helpers import (
    _install_runtime_dependencies_with_pip,
    _logs_path,
    _mcp_client_config_snippet,
    _open_in_system,
    _project_root,
    _resolve_uv_command,
    _run_command,
    _update_action_status,
    _uv_blender_mcp_command,
)


# ---------------------------------------------------------------------------
# Operator: Start Server
# ---------------------------------------------------------------------------
class BLENDERMCP_OT_StartServer(bpy.types.Operator):
    bl_idname = "blendermcp.start_server"
    bl_label = "Connect to LLM client"
    bl_description = "Start the BlenderMCP server to connect with your LLM client"

    def execute(self, context):
        # Import lazily to avoid circular imports
        import importlib
        addon_mod = importlib.import_module("addon")
        server_cls = addon_mod.BlenderMCPServer

        scene = context.scene
        if not hasattr(bpy.types, "blendermcp_server") or not bpy.types.blendermcp_server:
            bpy.types.blendermcp_server = server_cls(port=scene.blendermcp_port)

        bpy.types.blendermcp_server.start()
        scene.blendermcp_server_running = True
        _update_action_status(scene, "Connect to MCP server", True, f"Listening on port {scene.blendermcp_port}")
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

            self.report({"INFO"}, "Dependencies are ready (uv sync completed).")
            _update_action_status(context.scene, "Check/Install Dependencies", True, "uv sync completed")
            return {"FINISHED"}

        code, output = _install_runtime_dependencies_with_pip(root)
        if code != 0:
            self.report({"ERROR"}, "Fallback install failed. See Blender console for details.")
            if output:
                print("[blender-mcp] pip install output:")
                print(output)
            _update_action_status(context.scene, "Check/Install Dependencies", False, "pip fallback failed")
            return {"CANCELLED"}

        self.report({"INFO"}, "Runtime dependencies installed via Blender Python (pip).")
        _update_action_status(context.scene, "Check/Install Dependencies", True, "pip fallback completed")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Operator: Run MCP Server Terminal
# ---------------------------------------------------------------------------
class BLENDERMCP_OT_RunMCPServerTerminal(bpy.types.Operator):
    bl_idname = "blendermcp.run_mcp_terminal_server"
    bl_label = "Run MCP Server in Terminal"
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

        self.report({"INFO"}, f"MCP server terminal launched on {host}:{port}.")
        _update_action_status(context.scene, "Run MCP Server in Terminal", True, f"Started on {host}:{port}")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Operator: Copy MCP Client Config
# ---------------------------------------------------------------------------
class BLENDERMCP_OT_CopyMCPClientConfig(bpy.types.Operator):
    bl_idname = "blendermcp.copy_mcp_client_config"
    bl_label = "Copy MCP Client Config"
    bl_description = "Copy stdio config snippet for Claude/Cursor/Ollama/LM Studio"

    def execute(self, context):
        scene = context.scene
        client = scene.blendermcp_client_target
        snippet = _mcp_client_config_snippet(client, host="localhost", port=int(scene.blendermcp_port))
        context.window_manager.clipboard = snippet
        self.report({"INFO"}, f"Copied {client} MCP config to clipboard.")
        _update_action_status(scene, "Copy MCP Client Config", True, f"Client: {client}")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Operator: Health Check
# ---------------------------------------------------------------------------
class BLENDERMCP_OT_HealthCheck(bpy.types.Operator):
    bl_idname = "blendermcp.health_check"
    bl_label = "Health Check"
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

        self.report({"INFO"}, "Health check passed. See Blender console for details.")
        _update_action_status(context.scene, "Health Check", True, f"doctor ok for localhost:{port}")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Operator: Open Logs
# ---------------------------------------------------------------------------
class BLENDERMCP_OT_OpenLogs(bpy.types.Operator):
    bl_idname = "blendermcp.open_logs"
    bl_label = "Open Logs"
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

        self.report({"INFO"}, f"Opened logs: {path}")
        _update_action_status(context.scene, "Open Logs", True, os.path.basename(path))
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Operator: Clear Cache (MP-05)
# ---------------------------------------------------------------------------
class BLENDERMCP_OT_ClearCache(bpy.types.Operator):
    bl_idname = "blendermcp.clear_cache"
    bl_label = "Clear Asset Cache"
    bl_description = "Clear all cached downloaded assets from Poly Haven and Sketchfab"

    def execute(self, context):
        # Import lazily to get the global cache instance
        import importlib
        addon_mod = importlib.import_module("addon")
        deleted = addon_mod._asset_cache.clear()
        self.report({"INFO"}, f"Cleared {deleted} cached files")
        _update_action_status(context.scene, "Clear Cache", True, f"Deleted files: {deleted}")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Operator: Stop Server
# ---------------------------------------------------------------------------
class BLENDERMCP_OT_StopServer(bpy.types.Operator):
    bl_idname = "blendermcp.stop_server"
    bl_label = "Stop the LLM connection"
    bl_description = "Stop the connection to your LLM client"

    def execute(self, context):
        scene = context.scene
        if hasattr(bpy.types, "blendermcp_server") and bpy.types.blendermcp_server:
            bpy.types.blendermcp_server.stop()
            del bpy.types.blendermcp_server
        scene.blendermcp_server_running = False
        _update_action_status(scene, "Disconnect from MCP server", True, "Server stopped")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Modal Operator: Download Progress (MP-02)
# ---------------------------------------------------------------------------
class BLENDERMCP_OT_DownloadProgress(bpy.types.Operator):
    """Display download progress with cancellation support."""

    bl_idname = "blendermcp.download_progress"
    bl_label = "Download Progress"

    operation_id: bpy.props.StringProperty(default="")
    _timer = None
    _last_progress = 0

    def _get_progress_tracker(self):
        """Lazy import of progress tracker to avoid circular deps."""
        try:
            import importlib
            addon_mod = importlib.import_module("addon")
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
                self.report({"INFO"}, f"Download complete! ({progress_info.format_progress()})")
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
]
