"""Shared helper functions for BlenderMCP addon UI and operators."""

import json
import os
import platform
import subprocess
import sys
import time


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
    if os.name == "nt":
        candidates.append(["py", "-m", "uv"])
    return candidates


def _resolve_uv_command(cwd: str) -> list[str] | None:
    """Find a working uv command prefix or return None."""
    for prefix in _uv_command_prefixes():
        code, _ = _run_command([*prefix, "--version"], cwd=cwd)
        if code == 0:
            return prefix
    return None


def _uv_blender_mcp_command(cwd: str, host: str, port: int, doctor: bool = False) -> list[str] | None:
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
    return _run_command([sys.executable, "-m", "pip", "install", "--upgrade", "requests>=2.25.0"], cwd=cwd)


def _mcp_client_config_snippet(client: str, host: str, port: int) -> str:
    """Generate stdio config snippets for MCP-compatible clients."""
    args = ["run", "blender-mcp", "--host", host, "--port", str(port)]
    config = {"mcpServers": {"blender": {"command": "uv", "args": args}}}
    if client == "claude":
        return json.dumps(config, indent=2)
    if client == "cursor":
        return json.dumps(config, indent=2)
    if client == "lm_studio":
        return json.dumps(config, indent=2)
    if client == "ollama":
        return (
            "Use this in your MCP-capable Ollama client (Continue/Open WebUI/etc):\n"
            + json.dumps(config, indent=2)
        )
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
