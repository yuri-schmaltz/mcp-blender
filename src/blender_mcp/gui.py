"""PySide6 configuration UI for Blender MCP."""

from __future__ import annotations

import logging
import os
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from blender_mcp.logging_config import (
    DEFAULT_HANDLER,
    DEFAULT_LOG_FORMAT,
    DEFAULT_LOG_LEVEL,
    configure_logging,
)
from blender_mcp.server import DEFAULT_HOST, DEFAULT_PORT
from blender_mcp.i18n import _, get_i18n


ENV_FILE = Path(os.getenv("BLENDER_MCP_ENV_FILE", Path.home() / ".blender_mcp.env"))
VALID_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Status icons for accessibility
ICON_SUCCESS = "✅"
ICON_ERROR = "❌"
ICON_PROCESSING = "🔄"
ICON_WARNING = "⚠️"


@dataclass
class MCPConfig:
    """In-memory representation of MCP settings."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    log_level: str = DEFAULT_LOG_LEVEL
    log_format: str = DEFAULT_LOG_FORMAT
    log_handler: str = DEFAULT_HANDLER
    log_file: str = os.getenv("BLENDER_MCP_LOG_FILE", "blender_mcp.log")

    @classmethod
    def from_environment(cls) -> "MCPConfig":
        """Create a config object populated from environment variables."""

        return cls(
            host=os.getenv("BLENDER_HOST", DEFAULT_HOST),
            port=int(os.getenv("BLENDER_PORT", DEFAULT_PORT)),
            log_level=os.getenv("BLENDER_MCP_LOG_LEVEL", DEFAULT_LOG_LEVEL),
            log_format=os.getenv("BLENDER_MCP_LOG_FORMAT", DEFAULT_LOG_FORMAT),
            log_handler=os.getenv("BLENDER_MCP_LOG_HANDLER", DEFAULT_HANDLER),
            log_file=os.getenv("BLENDER_MCP_LOG_FILE", "blender_mcp.log"),
        )

    def to_environment(self) -> Dict[str, str]:
        """Return a mapping of environment variables for the current settings."""

        return {
            "BLENDER_HOST": self.host,
            "BLENDER_PORT": str(self.port),
            "BLENDER_MCP_LOG_LEVEL": self.log_level,
            "BLENDER_MCP_LOG_FORMAT": self.log_format,
            "BLENDER_MCP_LOG_HANDLER": self.log_handler,
            "BLENDER_MCP_LOG_FILE": self.log_file,
        }


def _load_env_file() -> Dict[str, str]:
    """Load persisted configuration from the user's env file."""

    if not ENV_FILE.exists():
        return {}

    values: Dict[str, str] = {}
    try:
        for line in ENV_FILE.read_text().splitlines():
            if not line or line.strip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
        os.environ.update(values)
    except OSError:
        # Ignore persistence issues and continue with defaults
        return {}

    return values


def _save_env_file(env: Dict[str, str]) -> None:
    """Persist the current environment mapping to the user's env file."""

    try:
        ENV_FILE.write_text("\n".join(f"{key}={value}" for key, value in env.items()))
    except OSError:
        # Persistence is best-effort; surface message in status label
        pass


class ConfigWindow(QWidget):
    """Main window that exposes all Blender MCP configuration knobs."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(_("app_title"))
        _load_env_file()
        self.config = MCPConfig.from_environment()
        self._build_ui()
        self._refresh_summary()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        form = QFormLayout()

        # Host field with inline validation
        self.host_edit = QLineEdit(self.config.host)
        self.host_edit.setAccessibleName("blender_host_input")
        self.host_edit.textChanged.connect(self._validate_host_field)
        self.host_edit.textChanged.connect(lambda _text: self._refresh_summary())
        form.addRow(_("host_label"), self.host_edit)
        self.host_error_label = QLabel("")
        self.host_error_label.setStyleSheet("color: #d32f2f; font-size: 11px;")
        form.addRow("", self.host_error_label)

        # Port field (already validated by QSpinBox range)
        self.port_spin = QSpinBox()
        self.port_spin.setAccessibleName("blender_port_input")
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(self.config.port)
        self.port_spin.valueChanged.connect(lambda _value: self._refresh_summary())
        form.addRow(_("port_label"), self.port_spin)

        # Log level (validated by combo box)
        self.level_combo = QComboBox()
        self.level_combo.setAccessibleName("log_level_select")
        self.level_combo.addItems(VALID_LEVELS)
        current_level = self.config.log_level.upper()
        index = self.level_combo.findText(current_level)
        if index >= 0:
            self.level_combo.setCurrentIndex(index)
        self.level_combo.currentTextChanged.connect(lambda _text: self._refresh_summary())
        form.addRow(_("log_level_label"), self.level_combo)

        # Format field with inline validation
        self.format_edit = QLineEdit(self.config.log_format)
        self.format_edit.setAccessibleName("log_format_input")
        self.format_edit.textChanged.connect(self._validate_format_field)
        self.format_edit.textChanged.connect(lambda _text: self._refresh_summary())
        form.addRow(_("log_format_label"), self.format_edit)
        self.format_error_label = QLabel("")
        self.format_error_label.setStyleSheet("color: #d32f2f; font-size: 11px;")
        form.addRow("", self.format_error_label)

        # Handler (validated by combo box)
        self.handler_combo = QComboBox()
        self.handler_combo.setAccessibleName("log_handler_select")
        self.handler_combo.addItem(_("console"), "console")
        self.handler_combo.addItem(_("file"), "file")
        handler_index = self.handler_combo.findData(self.config.log_handler.lower())
        if handler_index >= 0:
            self.handler_combo.setCurrentIndex(handler_index)
        self.handler_combo.currentIndexChanged.connect(lambda _index: self._refresh_summary())
        form.addRow(_("log_destination_label"), self.handler_combo)

        # Log file field with inline validation
        file_row = QHBoxLayout()
        self.log_file_edit = QLineEdit(self.config.log_file)
        self.log_file_edit.setAccessibleName("log_file_input")
        self.log_file_edit.textChanged.connect(self._validate_file_field)
        self.log_file_edit.textChanged.connect(lambda _text: self._refresh_summary())
        browse_button = QPushButton(_("browse_button"))
        browse_button.setAccessibleName("log_file_browse_button")
        browse_button.clicked.connect(self._browse_log_file)
        file_row.addWidget(self.log_file_edit)
        file_row.addWidget(browse_button)
        form.addRow(_("log_file_label"), file_row)
        self.file_error_label = QLabel("")
        self.file_error_label.setStyleSheet("color: #d32f2f; font-size: 11px;")
        form.addRow("", self.file_error_label)

        layout.addLayout(form)

        buttons = QHBoxLayout()
        self.apply_button = QPushButton(_("apply_button"))
        self.apply_button.setAccessibleName("apply_config_button")
        self.apply_button.clicked.connect(self._apply_changes)
        self.test_connection_button = QPushButton(_("test_connection_button"))
        self.test_connection_button.setAccessibleName("test_connection_button")
        self.test_connection_button.clicked.connect(self._test_connection)
        reset_button = QPushButton(_("reset_defaults_button"))
        reset_button.setAccessibleName("reset_defaults_button")
        reset_button.clicked.connect(self._reset_defaults)
        buttons.addWidget(self.apply_button)
        buttons.addWidget(self.test_connection_button)
        buttons.addWidget(reset_button)
        layout.addLayout(buttons)

        layout.addWidget(QLabel(_("environment_summary_label")))
        self.summary = QTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setMinimumHeight(150)
        layout.addWidget(self.summary)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        self.setLayout(layout)
        
        # Set tab order for keyboard navigation (QW-04)
        self.setTabOrder(self.host_edit, self.port_spin)
        self.setTabOrder(self.port_spin, self.level_combo)
        self.setTabOrder(self.level_combo, self.format_edit)
        self.setTabOrder(self.format_edit, self.handler_combo)
        self.setTabOrder(self.handler_combo, self.log_file_edit)
        self.setTabOrder(self.log_file_edit, browse_button)
        self.setTabOrder(browse_button, self.apply_button)
        self.setTabOrder(self.apply_button, self.test_connection_button)
        self.setTabOrder(self.test_connection_button, reset_button)
        self.setTabOrder(reset_button, self.summary)

    def _browse_log_file(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(self, "Selecionar arquivo de log", self.log_file_edit.text())
        if file_path:
            self.log_file_edit.setText(file_path)
            self._refresh_summary()
    
    def _validate_host_field(self, text: str) -> None:
        """Validate host field in real-time (MP-01)."""
        text = text.strip()
        if not text:
            self.host_edit.setStyleSheet("border: 2px solid #d32f2f;")
            self.host_error_label.setText(f"{ICON_ERROR} {_('error_host_empty')}")
            self.apply_button.setEnabled(False)
        else:
            self.host_edit.setStyleSheet("")
            self.host_error_label.setText("")
            self._update_apply_button_state()
    
    def _validate_format_field(self, text: str) -> None:
        """Validate log format field in real-time (MP-01)."""
        text = text.strip()
        if not text:
            self.format_edit.setStyleSheet("border: 2px solid #d32f2f;")
            self.format_error_label.setText(f"{ICON_ERROR} {_('error_format_empty')}")
            self.apply_button.setEnabled(False)
        elif not self._is_valid_log_format(text):
            self.format_edit.setStyleSheet("border: 2px solid #d32f2f;")
            self.format_error_label.setText(f"{ICON_ERROR} {_('error_format_invalid')}")
            self.apply_button.setEnabled(False)
        else:
            self.format_edit.setStyleSheet("")
            self.format_error_label.setText("")
            self._update_apply_button_state()
    
    def _validate_file_field(self, text: str) -> None:
        """Validate log file field in real-time (MP-01)."""
        text = text.strip()
        if not text:
            self.log_file_edit.setStyleSheet("border: 2px solid #d32f2f;")
            self.file_error_label.setText(f"{ICON_ERROR} {_('error_file_empty')}")
            self.apply_button.setEnabled(False)
        else:
            self.log_file_edit.setStyleSheet("")
            self.file_error_label.setText("")
            self._update_apply_button_state()
    
    def _update_apply_button_state(self) -> None:
        """Enable apply button only if all fields are valid (MP-01)."""
        host_valid = bool(self.host_edit.text().strip()) and not self.host_error_label.text()
        format_valid = bool(self.format_edit.text().strip()) and not self.format_error_label.text()
        file_valid = bool(self.log_file_edit.text().strip()) and not self.file_error_label.text()
        
        self.apply_button.setEnabled(host_valid and format_valid and file_valid)

    def _apply_changes(self) -> None:
        is_valid, message = self._validate_inputs()
        if not is_valid:
            self._set_status(message, error=True)
            return

        self._sync_config_from_widgets(allow_defaults=False)

        os.environ.update(self.config.to_environment())
        try:
            configure_logging(
                level=self.config.log_level,
                log_format=self.config.log_format,
                handler_type=self.config.log_handler,
            )
        except Exception as exc:  # pragma: no cover - surface to UI
            self._set_status(_("status_log_error", error=exc), error=True)
            return

        _save_env_file(self.config.to_environment())
        self._refresh_summary()
        self._set_status(_("status_applied"))

    def _reset_defaults(self) -> None:
        self.config = MCPConfig()
        self.host_edit.setText(self.config.host)
        self.port_spin.setValue(self.config.port)
        self.level_combo.setCurrentText(self.config.log_level)
        self.format_edit.setText(self.config.log_format)
        handler_index = self.handler_combo.findData(self.config.log_handler)
        if handler_index >= 0:
            self.handler_combo.setCurrentIndex(handler_index)
        self.log_file_edit.setText(self.config.log_file)
        self._refresh_summary()
        _save_env_file(self.config.to_environment())
        self._set_status(_("status_restored"))

    def _refresh_summary(self) -> None:
        self._sync_config_from_widgets()
        env_lines = [f"{key}={value}" for key, value in self.config.to_environment().items()]
        self.summary.setPlainText("\n".join(env_lines))

    def _sync_config_from_widgets(self, *, allow_defaults: bool = True) -> None:
        host = self.host_edit.text().strip()
        log_format = self.format_edit.text().strip()
        log_file = self.log_file_edit.text().strip()

        self.config.host = host or (DEFAULT_HOST if allow_defaults else "")
        self.config.port = int(self.port_spin.value())
        self.config.log_level = self.level_combo.currentText().upper()
        self.config.log_format = log_format or (DEFAULT_LOG_FORMAT if allow_defaults else "")
        selected_handler = self.handler_combo.currentData()
        if selected_handler:
            self.config.log_handler = str(selected_handler)
        else:
            self.config.log_handler = self.handler_combo.currentText().strip().lower()
        self.config.log_file = log_file or ("blender_mcp.log" if allow_defaults else "")

    def _validate_inputs(self) -> tuple[bool, str]:
        host = self.host_edit.text().strip()
        if not host:
            return False, "Host não pode ser vazio."

        if self.level_combo.currentText().upper() not in VALID_LEVELS:
            return False, "Nível de log inválido."

        log_format = self.format_edit.text().strip()
        if not log_format:
            return False, "Formato de log não pode ser vazio."
        if not self._is_valid_log_format(log_format):
            return False, "Formato de log inválido."

        if not self.log_file_edit.text().strip():
            return False, "Arquivo de log não pode ser vazio."

        return True, ""

    def _is_valid_log_format(self, log_format: str) -> bool:
        try:
            formatter = logging.Formatter(log_format)
            record = logging.LogRecord(
                name="test", level=logging.INFO, pathname=__file__, lineno=1, msg="msg", args=(), exc_info=None
            )
            formatter.format(record)
        except Exception:
            return False
        return True

    def _test_connection(self) -> None:
        host = self.host_edit.text().strip()
        port = int(self.port_spin.value())
        if not host:
            self._set_status(_("error_host_empty"), error=True)
            return

        # Disable button and show testing status
        self.test_connection_button.setEnabled(False)
        original_text = self.test_connection_button.text()
        self.test_connection_button.setText(_("status_testing"))
        self._set_status(f"{ICON_PROCESSING} {_('status_testing')}", error=False)
        
        try:
            with socket.create_connection((host, port), timeout=1):
                self._set_status(f"{ICON_SUCCESS} {_('status_success', host=host, port=port)}")
        except OSError as exc:
            error_msg = str(exc)
            # Provide user-friendly error messages
            if "refused" in error_msg.lower():
                self._set_status(f"{ICON_ERROR} {_('status_connection_refused')}", error=True)
            elif "timed out" in error_msg.lower():
                self._set_status(f"{ICON_ERROR} {_('status_timeout')}", error=True)
            else:
                self._set_status(f"{ICON_ERROR} {_('status_connection_failed', host=host, port=port, error=exc)}", error=True)
        finally:
            # Re-enable button
            self.test_connection_button.setEnabled(True)
            self.test_connection_button.setText(original_text)

    def _set_status(self, message: str, *, error: bool = False) -> None:
        # Add icon prefix if not already present (QW-03)
        if not message.startswith((ICON_SUCCESS, ICON_ERROR, ICON_PROCESSING, ICON_WARNING)):
            icon = ICON_ERROR if error else ICON_SUCCESS
            message = f"{icon} {message}"
        
        self.status_label.setText(message)
        color = "#d32f2f" if error else "#2e7d32"
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")


def launch_gui() -> None:
    """Start the PySide6 application that exposes MCP configuration."""

    app = QApplication(sys.argv)
    window = ConfigWindow()
    window.resize(640, 420)
    window.show()
    app.exec()


def main() -> None:
    """Entrypoint used by console script `blender-mcp-gui`."""
    launch_gui()


if __name__ == "__main__":
    launch_gui()
