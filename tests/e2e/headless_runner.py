"""Run Blender in --background mode with the MCP addon enabled and the
socket server started. Drives the round-trip smoke test from the outside.

Usage (inside Blender's embedded Python)::

    blender --background --python tests/e2e/headless_runner.py

Environment variables:
    BLENDER_MCP_HARNESS_PORT       Port to bind the socket server on.
    BLENDER_MCP_HARNESS_KEEPALIVE How long to keep Blender alive (seconds).
    MCP_REPO_ROOT                 Path to the repo (default /workspace/mcp-blender).

Why this is not just ``addon.register()``:
    The addon registers an operator (``bpy.ops.blendermcp.start_server``)
    that needs a 3D-viewport context. In ``--background`` mode there is no
    such context, so we instantiate the server directly. The class is the
    production :class:`addon.server.BlenderMCPServer`.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
import traceback
from pathlib import Path


def _candidate_is_on_path(candidate: Path) -> bool:
    """Return True if ``candidate`` (or its ``modules`` subdir) is on
    :data:`sys.path`. Blender 4.x adds ``scripts/addons`` to sys.path;
    5.0+ adds ``scripts/addons/modules`` instead.
    """
    candidates_to_test = [candidate, candidate / "modules"]
    try:
        import bpy  # type: ignore

        paths = list(bpy.utils.user_resource("SCRIPTS").split(os.sep))  # noqa: F841
    except Exception:
        pass
    sys_path_strs = [str(p) for p in sys.path]
    for c in candidates_to_test:
        cs = str(c)
        if cs in sys_path_strs:
            return True
    return False


def main() -> None:
    import bpy  # type: ignore  # Blender builtin

    # ------------------------------------------------------------------
    # 0. Pump bpy.app.timers inline: in --background mode Blender does
    #    not drive its event loop, so timer-registered callbacks (the
    #    way the addon dispatches commands to the main thread) never
    #    fire. We replace timers.register with a thin wrapper that runs
    #    the callable immediately on the caller's thread — safe because
    #    Blender's main thread is *the* thread in --background mode.
    # ------------------------------------------------------------------
    _orig_timer_register = bpy.app.timers.register

    def _pumped_register(func, *, first_interval=0.0, persistent=False):
        # Run now. Skip first_interval semantics; we never sleep here.
        try:
            func()
        except Exception:
            import traceback as _tb

            _tb.print_exc()
        # Return a no-op handle so callers that .pop() it are happy.
        class _Handle:
            pass

        return _Handle()

    bpy.app.timers.register = _pumped_register
    # Keep the original around just in case some caller needs it.
    bpy.app.timers._original_register = _orig_timer_register  # type: ignore[attr-defined]

    repo_root = Path(os.environ.get("MCP_REPO_ROOT", "/workspace/mcp-blender"))
    addon_id = os.environ.get("BLENDER_MCP_ADDON_ID", "blender_mcp_local")
    port = int(os.getenv("BLENDER_MCP_HARNESS_PORT", "9876"))
    keep_alive = float(os.getenv("BLENDER_MCP_HARNESS_KEEPALIVE", "120"))

    # Force a strict payload cap on the addon side. The smoke test sends
    # a payload ~8 KiB to verify the cap is enforced.
    os.environ.setdefault("BLENDER_MCP_MAX_PAYLOAD_BYTES", "2048")

    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    # ------------------------------------------------------------------
    # 1. Install the addon in a discoverable location.
    #    Blender 5.0+ moved user-installed modules under
    #    ``scripts/addons/modules`` (was ``scripts/addons`` in 4.x).
    #    We write to both paths so the harness works on either.
    # ------------------------------------------------------------------
    version_dir = ".".join(str(n) for n in bpy.app.version[:2])
    user_scripts = (
        Path(os.environ.get("HOME", "~")) / ".config" / "blender" / version_dir / "scripts"
    )
    candidates = [
        # (target, sys_path_entry) pairs
        # Prefer 5.0+ path: user addons live under ``addons/modules`` so
        # they are top-level importable names. Older 4.x uses ``addons``
        # directly. Check the 5.0+ variant first because the directory
        # also passes the 4.x probe (when both are on sys.path), and we
        # would otherwise install at the wrong level.
        (user_scripts / "addons" / "modules", user_scripts / "addons" / "modules"),  # 5.0+
        (user_scripts / "addons", user_scripts / "addons"),                # 4.x
    ]
    sys_path_strs = [str(p) for p in sys.path]
    chosen = None
    for target_dir, sys_path_dir in candidates:
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        if str(sys_path_dir) not in sys_path_strs:
            continue
        chosen = target_dir / addon_id
        break
    if chosen is None:
        chosen = candidates[-1][0] / addon_id
        candidates[-1][0].mkdir(parents=True, exist_ok=True)
    target = chosen
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    # Blender loads ``<addon_id>/__init__.py``. The repo's __init__.py
    # registers the AddonPreferences class (with the correct bl_idname)
    # and then loads the legacy ``addon.py`` which holds the socket
    # server. Both files are needed; the legacy ``addon/`` subdirectory
    # lives next to them.
    shutil.copy(repo_root / "__init__.py", target / "__init__.py")
    shutil.copy(repo_root / "addon.py", target / "addon.py")
    if (target / "blender_manifest.toml").exists():
        (target / "blender_manifest.toml").unlink()
    shutil.copy(repo_root / "blender_manifest.toml", target / "blender_manifest.toml")
    shutil.copytree(repo_root / "addon", target / "addon")

    print(f"BLENDERMCP_HARNESS: installed at {target}", flush=True)

    # ------------------------------------------------------------------
    # 2. Enable the addon (this runs register() with __package__ set).
    #    Blender 5.x renamed the ``refresh`` keyword of
    #    ``addon_utils.enable`` to ``refresh_handled``; older releases
    #    (4.2-) take ``refresh=True``. We probe both.
    # ------------------------------------------------------------------
    import addon_utils  # type: ignore

    def _enable_with_refresh(name):
        """Best-effort ``enable`` call across Blender 4.x / 5.x APIs."""
        for kw in ("refresh_handled", "refresh"):
            try:
                addon_utils.enable(
                    name,
                    default_set=False,
                    persistent=False,
                    **{kw: True},
                )
                return
            except TypeError:
                continue
        # No compatible keyword found, fall through to plain enable.
        addon_utils.enable(name, default_set=False, persistent=False)

    try:
        addon_utils.modules_refresh()
        # Clear any negative import cache (Blender 5.x caches the
        # "module not found" error and refuses to retry without help).
        import importlib

        importlib.invalidate_caches()
        # Drop the addon from sys.modules if a previous test left a
        # broken partial import in place.
        sys.modules.pop(addon_id, None)
        sys.modules.pop("addon_mcp_local", None)  # historical name
        _enable_with_refresh(addon_id)
    except Exception as exc:
        print(f"BLENDERMCP_HARNESS: addon_utils.enable failed: {exc!r}", flush=True)

    # Whether addon_utils.enable succeeded or not, the operator path
    # is what populates ``bpy.context.preferences.addons[id]`` in
    # Blender 5.x. Run it as a follow-up.
    try:
        bpy.ops.preferences.addon_enable(module=addon_id)
    except Exception as exc:
        print(f"BLENDERMCP_HARNESS: bpy.ops.addon_enable failed: {exc!r}", flush=True)

    if addon_id not in sys.modules:
        print(f"BLENDERMCP_HARNESS: {addon_id!r} not in sys.modules after enable", flush=True)
        return

    addon_mod = sys.modules[addon_id]
    print(f"BLENDERMCP_HARNESS: addon module loaded as {addon_id!r}", flush=True)

    # ------------------------------------------------------------------
    # Flip the global preferences so handlers like ``execute_code`` work.
    # Without this the production behaviour is "deny by default".
    # ------------------------------------------------------------------
    try:
        addon_entry = bpy.context.preferences.addons[addon_id]
        prefs = addon_entry.preferences
        if prefs is None:
            raise RuntimeError("addon preferences is None")
        prefs.allow_code_execution = True
        print("BLENDERMCP_HARNESS: allow_code_execution = True", flush=True)
    except Exception as _exc:
        print(f"BLENDERMCP_HARNESS: cannot flip prefs: {_exc}", flush=True)

    # ------------------------------------------------------------------
    # 3. Start the socket server (bypass operator: no UI context here).
    #    The upstream ``__init__.py`` loads ``addon.py`` via the private
    #    helper ``_load_addon_module`` and stashes it on the module's
    #    ``_addon_mod`` global, which we read back here.
    # ------------------------------------------------------------------
    loaded_addon = getattr(addon_mod, "_addon_mod", None) or sys.modules.get(
        f"{addon_id}.addon"
    )
    if loaded_addon is None:
        raise RuntimeError("addon sub-module not loaded")
    server_cls = loaded_addon.SocketBlenderMCPServer
    srv = server_cls(host="127.0.0.1", port=port, client_timeout=30.0)
    srv.command_executor = loaded_addon.execute_command
    srv.start()
    print(f"BLENDERMCP_HARNESS: socket listening on 127.0.0.1:{port}", flush=True)
    print(f"BLENDERMCP_SMOKE_READY:{port}", flush=True)

    try:
        end = time.time() + keep_alive
        while time.time() < end and srv.running:
            time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            srv.stop()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        # Don't raise -- Blender swallows the return code anyway, but we
        # want a clear traceback on the console.
        sys.exit(1)
