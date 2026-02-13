"""Bootstrap script executed by Blender for smoke integration tests.

Starts the addon socket server on a dynamic port and keeps Blender alive
long enough for the pytest process to run MCP socket commands.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import traceback
from pathlib import Path


def _prepare_imports() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))


def main() -> None:
    _prepare_imports()
    import bpy  # type: ignore

    addon_path = Path(__file__).resolve().parents[2] / "addon.py"
    spec = importlib.util.spec_from_file_location("blendermcp_addon_runtime", addon_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load addon module from {addon_path}")
    addon = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(addon)

    port = int(os.getenv("BLENDER_MCP_SMOKE_PORT", "9876"))
    try:
        addon.register()
        bpy.context.scene.blendermcp_port = port
        bpy.ops.blendermcp.start_server()
        print(f"BLENDERMCP_SMOKE_READY:{port}", flush=True)
    except Exception as exc:  # pragma: no cover - executed in Blender process
        print(f"BLENDERMCP_SMOKE_ERROR:{exc}", flush=True)
        traceback.print_exc()


if __name__ == "__main__":
    main()
