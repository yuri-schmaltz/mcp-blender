"""Shared helper functions for BlenderMCP addon UI and operators."""

import json
import os
import platform
import shutil
import subprocess
import sys
import time

import bpy


def resolve_addon_package(caller_package=None):
    """Resolve the root extension/addon package name for addon preferences lookup.

    In Blender 4.2+ Extension mode, __package__ for sub-modules is e.g.
    'bl_ext.user_default.mcp_blender.addon.handlers' — we need only the first
    3 parts: 'bl_ext.user_default.mcp_blender'.

    Args:
        caller_package: The __package__ of the calling module. If None, uses
                        the helpers module's own __package__.

    Returns:
        The root package name suitable for bpy.context.preferences.addons lookup.
    """
    pkg = caller_package or __package__
    if not pkg:
        return "mcp_blender"
    if pkg.startswith("bl_ext."):
        parts = pkg.split(".")
        return ".".join(parts[:3]) if len(parts) >= 3 else pkg
    return pkg.split(".")[0]


def get_addon_prefs(caller_package=None):
    """Access global addon preferences safely from any sub-module.

    Args:
        caller_package: The __package__ of the calling module.

    Returns:
        The AddonPreferences instance, or None if not found.
    """
    root_pkg = resolve_addon_package(caller_package)
    if bpy.context.preferences and root_pkg in bpy.context.preferences.addons:
        return bpy.context.preferences.addons[root_pkg].preferences
    return None


def ensure_mode(mode: str):
    """Decorator to ensure Blender is in the correct mode before running a function.

    Supported modes: 'OBJECT', 'EDIT', 'POSE', 'SCULPT', 'VERTEX_PAINT', 'WEIGHT_PAINT', 'TEXTURE_PAINT'.
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            if bpy.context.mode != mode:
                try:
                    bpy.ops.object.mode_set(mode=mode)
                except Exception as e:
                    return {
                        "error": f"Failed to switch to {mode} (Current: {bpy.context.mode}): {str(e)}"
                    }
            return func(*args, **kwargs)

        return wrapper

    return decorator


# ── Client auto-detection ───────────────────────────────────────────────

# Full static list used as fallback when nothing is detected.
_ALL_CLIENTS: list[tuple[str, str, str]] = [
    ("claude", "Claude Desktop", "Copy config snippet for Claude Desktop"),
    ("cursor", "Cursor", "Copy config snippet for Cursor"),
    ("ollama", "Ollama", "Copy config snippet for an MCP-capable Ollama client"),
    ("lm_studio", "LM Studio", "Copy config snippet for LM Studio"),
    ("cherry_studio", "Cherry Studio", "Copy config snippet for Cherry Studio"),
]


def _is_ollama_installed() -> bool:
    """Check if Ollama is available on the system."""
    if shutil.which("ollama"):
        return True
    # Common install locations not in PATH
    home = os.path.expanduser("~")
    for candidate in [
        os.path.join(home, ".local", "bin", "ollama"),
        "/usr/local/bin/ollama",
        "/usr/bin/ollama",
    ]:
        if os.path.isfile(candidate):
            return True
    if os.name == "nt":
        appdata = os.environ.get("LOCALAPPDATA", "")
        if appdata and os.path.isfile(os.path.join(appdata, "Ollama", "ollama.exe")):
            return True
    return False


def _is_claude_installed() -> bool:
    """Check if Claude Desktop config directory exists."""
    home = os.path.expanduser("~")
    plat = platform.system()
    if plat == "Linux":
        return os.path.isdir(os.path.join(home, ".config", "Claude"))
    if plat == "Darwin":
        return os.path.isdir(os.path.join(home, "Library", "Application Support", "Claude"))
    if plat == "Windows":
        appdata = os.environ.get("APPDATA", "")
        return bool(appdata) and os.path.isdir(os.path.join(appdata, "Claude"))
    return False


def _is_cursor_installed() -> bool:
    """Check if Cursor config directory exists."""
    home = os.path.expanduser("~")
    plat = platform.system()
    if plat == "Linux":
        return os.path.isdir(os.path.join(home, ".config", "Cursor"))
    if plat == "Darwin":
        return os.path.isdir(os.path.join(home, "Library", "Application Support", "Cursor"))
    if plat == "Windows":
        appdata = os.environ.get("APPDATA", "")
        return bool(appdata) and os.path.isdir(os.path.join(appdata, "Cursor"))
    return False


def _is_lm_studio_installed() -> bool:
    """Check if LM Studio is available on the system."""
    if shutil.which("lms"):
        return True
    home = os.path.expanduser("~")
    plat = platform.system()
    if plat == "Linux":
        return os.path.isdir(os.path.join(home, ".cache", "lm-studio"))
    if plat == "Darwin":
        return os.path.isdir(os.path.join(home, "Library", "Application Support", "LM Studio"))
    if plat == "Windows":
        appdata = os.environ.get("LOCALAPPDATA", "")
        return bool(appdata) and os.path.isdir(os.path.join(appdata, "LM Studio"))

    return False


def _is_cherry_studio_installed() -> bool:
    """Check if Cherry Studio is installed (based on config dir)."""
    system = platform.system()
    if system == "Windows":
        path = os.path.expandvars(r"%APPDATA%\cherry-studio")
        if not os.path.isdir(path):
            path = os.path.expandvars(r"%USERPROFILE%\.cherrystudio")
    elif system == "Darwin":
        path = os.path.expanduser("~/Library/Application Support/cherry-studio")
        if not os.path.isdir(path):
            path = os.path.expanduser("~/.cherrystudio")
    else:  # Linux
        path = os.path.expanduser("~/.config/cherry-studio")
        if not os.path.isdir(path):
            path = os.path.expanduser("~/.cherrystudio")

    return os.path.isdir(path)


def detect_installed_clients() -> list[tuple[str, str, str]]:
    """Return Blender EnumProperty items for detected clients.

    Ollama is placed first when detected so it becomes the default.
    If no client is detected, the full static list is returned as fallback.
    """
    detected: list[tuple[str, str, str]] = []

    # We check each one and map to our static list
    # _ALL_CLIENTS indices: 0:claude, 1:cursor, 2:ollama, 3:lm_studio
    if _is_ollama_installed():
        detected.append(_ALL_CLIENTS[2])
    if _is_claude_installed():
        detected.append(_ALL_CLIENTS[0])
    if _is_cursor_installed():
        detected.append(_ALL_CLIENTS[1])
    if _is_lm_studio_installed():
        detected.append(_ALL_CLIENTS[3])
    if _is_cherry_studio_installed():
        detected.append(_ALL_CLIENTS[4])

    if not detected:
        return list(_ALL_CLIENTS)

    # Ensure Ollama is first (= Blender default) when present
    # (It's already first because we appended it first, but let's be explicit)
    ollama_items = [c for c in detected if c[0] == "ollama"]
    others = [c for c in detected if c[0] != "ollama"]
    return ollama_items + others


def _project_root() -> str:
    """Return repository root path based on addon package location."""
    # addon/utils/helpers.py -> addon/utils -> addon -> project_root
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _run_command(command: list[str], cwd: str) -> tuple[int, str]:
    """Run command and return exit code + combined output."""
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=1200,
            check=False,
        )
    except FileNotFoundError:
        return 127, f"Command not found: {command[0]}"
    except Exception as exc:
        return 1, str(exc)

    output = (completed.stdout or "").strip()
    err = (completed.stderr or "").strip()
    combined = "\n".join(part for part in [output, err] if part)
    return completed.returncode, combined


def _uv_command_prefixes() -> list[list[str]]:
    """Return candidate command prefixes to invoke uv across environments."""
    candidates = [["uv"], [sys.executable, "-m", "uv"]]
    # Common install locations not in Blender's PATH
    home = os.path.expanduser("~")
    for bindir in [
        os.path.join(home, ".local", "bin"),
        os.path.join(home, ".cargo", "bin"),
        "/usr/local/bin",
    ]:
        uv_path = os.path.join(bindir, "uv")
        if os.path.isfile(uv_path):
            candidates.append([uv_path])
    if os.name == "nt":
        candidates.append(["py", "-m", "uv"])
        appdata = os.environ.get("LOCALAPPDATA", "")
        if appdata:
            win_uv = os.path.join(appdata, "uv", "uv.exe")
            if os.path.isfile(win_uv):
                candidates.append([win_uv])
    return candidates


def _resolve_uv_command(cwd: str) -> list[str] | None:
    """Find a working uv command prefix or return None."""
    for prefix in _uv_command_prefixes():
        code, _ = _run_command([*prefix, "--version"], cwd=cwd)
        if code == 0:
            return prefix
    return None


def _uv_blender_mcp_command(
    cwd: str, host: str, port: int, doctor: bool = False
) -> list[str] | None:
    """Build a uv command that works both in repo checkout and installed addon mode."""
    uv_prefix = _resolve_uv_command(cwd)
    if uv_prefix is None:
        return None

    pyproject_path = os.path.join(cwd, "pyproject.toml")
    if os.path.exists(pyproject_path):
        cmd = [*uv_prefix, "run", "blender-mcp", "--host", host, "--port", str(port)]
    else:
        cmd = [*uv_prefix, "tool", "run", "blender-mcp", "--host", host, "--port", str(port)]

    if doctor:
        cmd.insert(-4, "--doctor")
    return cmd


def extend_sys_path_with_venv():
    """Auto-detect the virtual environment (.venv) in the repository root and add its site-packages to sys.path."""
    root = _project_root()
    for candidate in [root, os.path.dirname(root)]:
        venv_dir = os.path.join(candidate, ".venv")
        if os.path.exists(venv_dir):
            paths_to_add = []
            # Windows
            win_site = os.path.join(venv_dir, "Lib", "site-packages")
            if os.path.exists(win_site):
                paths_to_add.append(win_site)
            # Unix (Linux / macOS)
            unix_lib = os.path.join(venv_dir, "lib")
            if os.path.exists(unix_lib):
                try:
                    for item in os.listdir(unix_lib):
                        if item.startswith("python"):
                            unix_site = os.path.join(unix_lib, item, "site-packages")
                            if os.path.exists(unix_site):
                                paths_to_add.append(unix_site)
                except Exception:
                    pass
            for path in paths_to_add:
                if path not in sys.path:
                    sys.path.insert(0, path)
                    print(f"[blender-mcp] Added site-packages to sys.path: {path}")
            break


def _ensure_pip(cwd: str) -> tuple[bool, str]:
    """Ensure pip is available in current Python runtime."""
    code, out = _run_command([sys.executable, "-m", "pip", "--version"], cwd=cwd)
    if code == 0:
        return True, out
    code, out = _run_command([sys.executable, "-m", "ensurepip", "--upgrade"], cwd=cwd)
    if code != 0:
        return False, out
    code, out = _run_command([sys.executable, "-m", "pip", "--version"], cwd=cwd)
    return code == 0, out


def _install_runtime_dependencies_with_pip(cwd: str) -> tuple[int, str]:
    """Install minimal runtime deps when repo metadata is not available."""
    ok, out = _ensure_pip(cwd)
    if not ok:
        return 1, f"pip unavailable: {out}"
    return _run_command(
        [sys.executable, "-m", "pip", "install", "--upgrade", "requests>=2.25.0", "litellm>=1.0.0"],
        cwd=cwd,
    )


def _mcp_client_config_snippet(client: str, host: str, port: int) -> str:
    """Generate stdio config snippets for MCP-compatible clients.

    Uses the resolved absolute path to uv/uvx when available, so that
    desktop apps (LM Studio, etc.) that don't inherit the user's shell
    PATH can still find the binary.
    """
    # Try to find the real uvx path for desktop app compatibility
    home = os.path.expanduser("~")
    uvx_cmd = "uvx"  # fallback
    for bindir in [
        os.path.join(home, ".local", "bin"),
        os.path.join(home, ".cargo", "bin"),
        "/usr/local/bin",
    ]:
        candidate = os.path.join(bindir, "uvx")
        if os.path.isfile(candidate):
            uvx_cmd = candidate
            break

    config = {"mcpServers": {"blender": {"command": uvx_cmd, "args": ["blender-mcp"]}}}
    return json.dumps(config, indent=2)


def _update_action_status(scene, action: str, ok: bool, details: str = "") -> None:
    """Persist last action result in scene properties for UI visibility."""
    scene.blendermcp_last_action = action
    scene.blendermcp_last_action_ok = ok
    scene.blendermcp_last_action_details = details[:500]
    scene.blendermcp_last_action_at = time.strftime("%Y-%m-%d %H:%M:%S")


def _logs_path() -> str:
    """Resolve current log path from env or default value."""
    log_file = os.getenv("BLENDER_MCP_LOG_FILE", "blender_mcp.log")
    if os.path.isabs(log_file):
        return log_file
    return os.path.join(_project_root(), log_file)


def _open_in_system(path: str) -> None:
    """Open path using platform default app/file manager."""
    if os.name == "nt":
        os.startfile(path)
        return
    if platform.system() == "Darwin":
        subprocess.Popen(["open", path])
        return
    subprocess.Popen(["xdg-open", path])
