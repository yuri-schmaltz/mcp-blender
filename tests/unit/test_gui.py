"""GUI validation tests running in headless mode."""

from __future__ import annotations

import importlib
import os
from collections.abc import Generator

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app() -> Generator[QApplication, None, None]:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def gui_window(
    monkeypatch, tmp_path, app
):  # noqa: ARG001 - app fixture ensures QApplication exists
    env_file = tmp_path / "config.env"
    monkeypatch.setenv("BLENDER_MCP_ENV_FILE", str(env_file))

    import blender_mcp.gui as gui

    gui = importlib.reload(gui)
    window = gui.ConfigWindow()
    yield window


def test_invalid_host_triggers_error(gui_window):
    gui_window.host_edit.setText("")
    gui_window.format_edit.setText("%(message)s")

    QTest.mouseClick(gui_window.apply_button, Qt.LeftButton)

    assert gui_window.apply_button.isEnabled() is False
    assert gui_window.host_error_label.text()


def test_invalid_format_triggers_error(gui_window):
    gui_window.host_edit.setText("localhost")
    gui_window.format_edit.setText("%(missing_key)s")

    QTest.mouseClick(gui_window.apply_button, Qt.LeftButton)

    assert gui_window.apply_button.isEnabled() is False
    assert gui_window.format_error_label.text()


def test_to_environment_reflects_changes(gui_window):
    gui_window.host_edit.setText("example.org")
    gui_window.port_spin.setValue(5555)
    gui_window.level_combo.setCurrentText("DEBUG")
    gui_window.format_edit.setText("%(message)s")
    gui_window.handler_combo.setCurrentText("console")
    gui_window.log_file_edit.setText("custom.log")

    gui_window._sync_config_from_widgets(allow_defaults=False)
    env = gui_window.config.to_environment()

    assert env["BLENDER_HOST"] == "example.org"
    assert env["BLENDER_PORT"] == "5555"
    assert env["BLENDER_MCP_LOG_LEVEL"] == "DEBUG"
    assert env["BLENDER_MCP_LOG_FORMAT"] == "%(message)s"
    assert env["BLENDER_MCP_LOG_HANDLER"] == "console"
    assert env["BLENDER_MCP_LOG_FILE"] == "custom.log"


def test_handler_uses_canonical_value_when_label_changes(gui_window):
    gui_window.handler_combo.setItemText(0, "Console traduzido")
    gui_window.handler_combo.setCurrentIndex(0)
    gui_window.host_edit.setText("localhost")
    gui_window.format_edit.setText("%(message)s")
    gui_window.log_file_edit.setText("custom.log")

    gui_window._sync_config_from_widgets(allow_defaults=False)
    env = gui_window.config.to_environment()

    assert env["BLENDER_MCP_LOG_HANDLER"] == "console"
