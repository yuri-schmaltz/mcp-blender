from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])

    import blender_mcp.gui as gui

    gui = importlib.reload(gui)
    window = gui.ConfigWindow()
    window.resize(640, 420)
    window.show()
    app.processEvents()

    output_path = Path(os.getenv("BLENDER_MCP_VISUAL_ARTIFACT", "visual-artifacts/gui_current.png"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    window.grab().save(str(output_path), "PNG")
    print(f"Saved GUI snapshot to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
