"""PySide6 configuration UI for Blender MCP."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
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


class ConfigWindow(QWidget):
    """Main window that exposes all Blender MCP configuration knobs."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Blender MCP - Configurações")
        self.config = MCPConfig.from_environment()
        self._build_ui()
        self._refresh_summary()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        form = QFormLayout()

        self.host_edit = QLineEdit(self.config.host)
        form.addRow("Host do Blender", self.host_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(self.config.port)
        form.addRow("Porta", self.port_spin)

        self.level_combo = QComboBox()
        self.level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        current_level = self.config.log_level.upper()
        index = self.level_combo.findText(current_level)
        if index >= 0:
            self.level_combo.setCurrentIndex(index)
        form.addRow("Nível de log", self.level_combo)

        self.format_edit = QLineEdit(self.config.log_format)
        form.addRow("Formato de log", self.format_edit)

        self.handler_combo = QComboBox()
        self.handler_combo.addItems(["console", "file"])
        handler_index = self.handler_combo.findText(self.config.log_handler.lower())
        if handler_index >= 0:
            self.handler_combo.setCurrentIndex(handler_index)
        form.addRow("Destino do log", self.handler_combo)

        file_row = QHBoxLayout()
        self.log_file_edit = QLineEdit(self.config.log_file)
        browse_button = QPushButton("Escolher arquivo")
        browse_button.clicked.connect(self._browse_log_file)
        file_row.addWidget(self.log_file_edit)
        file_row.addWidget(browse_button)
        form.addRow("Arquivo de log", file_row)

        layout.addLayout(form)

        buttons = QHBoxLayout()
        apply_button = QPushButton("Aplicar e configurar")
        apply_button.clicked.connect(self._apply_changes)
        reset_button = QPushButton("Restaurar padrão")
        reset_button.clicked.connect(self._reset_defaults)
        buttons.addWidget(apply_button)
        buttons.addWidget(reset_button)
        layout.addLayout(buttons)

        layout.addWidget(QLabel("Resumo das variáveis de ambiente"))
        self.summary = QTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setMinimumHeight(150)
        layout.addWidget(self.summary)

        self.setLayout(layout)

    def _browse_log_file(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(self, "Selecionar arquivo de log", self.log_file_edit.text())
        if file_path:
            self.log_file_edit.setText(file_path)
            self._refresh_summary()

    def _apply_changes(self) -> None:
        self._sync_config_from_widgets()

        os.environ.update(self.config.to_environment())
        configure_logging(
            level=self.config.log_level,
            log_format=self.config.log_format,
            handler_type=self.config.log_handler,
        )
        self._refresh_summary()

    def _reset_defaults(self) -> None:
        self.config = MCPConfig()
        self.host_edit.setText(self.config.host)
        self.port_spin.setValue(self.config.port)
        self.level_combo.setCurrentText(self.config.log_level)
        self.format_edit.setText(self.config.log_format)
        self.handler_combo.setCurrentText(self.config.log_handler)
        self.log_file_edit.setText(self.config.log_file)
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        self._sync_config_from_widgets()
        env_lines = [f"{key}={value}" for key, value in self.config.to_environment().items()]
        self.summary.setPlainText("\n".join(env_lines))

    def _sync_config_from_widgets(self) -> None:
        self.config.host = self.host_edit.text().strip() or DEFAULT_HOST
        self.config.port = int(self.port_spin.value())
        self.config.log_level = self.level_combo.currentText()
        self.config.log_format = self.format_edit.text().strip() or DEFAULT_LOG_FORMAT
        self.config.log_handler = self.handler_combo.currentText()
        self.config.log_file = self.log_file_edit.text().strip() or "blender_mcp.log"


def launch_gui() -> None:
    """Start the PySide6 application that exposes MCP configuration."""

    app = QApplication(sys.argv)
    window = ConfigWindow()
    window.resize(640, 420)
    window.show()
    app.exec()


if __name__ == "__main__":
    launch_gui()
