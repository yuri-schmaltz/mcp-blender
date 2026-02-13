from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

BASELINE_IMAGE = (
    Path(__file__).resolve().parents[2] / "assets" / "baseline" / "gui_config_window.png"
)


def _pixel_diff_ratio(actual, baseline) -> float:
    width = actual.width()
    height = actual.height()
    total = width * height
    different = 0

    for y in range(height):
        for x in range(width):
            if actual.pixel(x, y) != baseline.pixel(x, y):
                different += 1

    return different / total if total else 0.0


@pytest.mark.visual
def test_gui_visual_regression(tmp_path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])

    env_file = tmp_path / "gui.env"
    monkeypatch.setenv("BLENDER_MCP_ENV_FILE", str(env_file))

    import blender_mcp.gui as gui

    gui = importlib.reload(gui)
    window = gui.ConfigWindow()
    window.resize(640, 420)
    window.show()
    app.processEvents()

    current_path = tmp_path / "gui_config_window_current.png"
    window.grab().save(str(current_path), "PNG")

    if os.getenv("BLENDER_MCP_UPDATE_BASELINE") == "1":
        BASELINE_IMAGE.parent.mkdir(parents=True, exist_ok=True)
        current_path.replace(BASELINE_IMAGE)
        pytest.skip("Baseline updated. Re-run without BLENDER_MCP_UPDATE_BASELINE=1.")

    if not BASELINE_IMAGE.exists():
        pytest.skip(
            f"Visual baseline missing: {BASELINE_IMAGE}. "
            "Run with BLENDER_MCP_UPDATE_BASELINE=1 to create it."
        )

    from PySide6.QtGui import QImage

    actual = QImage(str(current_path))
    baseline = QImage(str(BASELINE_IMAGE))

    assert actual.size() == baseline.size(), "GUI screenshot size changed from baseline"

    diff_ratio = _pixel_diff_ratio(actual, baseline)
    assert diff_ratio <= 0.02, f"Visual regression above threshold: {diff_ratio:.2%}"
