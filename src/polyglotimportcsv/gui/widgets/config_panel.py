"""The card that picks the two JSON configuration files."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)
from PySide6.QtCore import Signal

HINT = (
    "Ambos os arquivos são validados por JSON Schema antes da execução. "
    "A configuração de importação só pode referenciar SGBDs declarados na "
    "configuração de conexão."
)
FIELDS = ("config_path", "sgbd_config_path")


class ConfigPanel(QGroupBox):
    """Two rows: import configuration and DBMS configuration."""

    changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Arquivos de configuração", parent)
        self.config_edit = QLineEdit(self)
        self.sgbd_edit = QLineEdit(self)
        self.error_label = QLabel("", self)
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)

        hint = QLabel(HINT, self)
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)

        config_button = QPushButton("Procurar…", self)
        sgbd_button = QPushButton("Procurar…", self)
        config_button.clicked.connect(self._browse_config)
        sgbd_button.clicked.connect(self._browse_sgbd)

        layout = QGridLayout(self)
        layout.addWidget(QLabel("Configuração de importação (--config)", self), 0, 0)
        layout.addWidget(self.config_edit, 0, 1)
        layout.addWidget(config_button, 0, 2)
        layout.addWidget(QLabel("Configuração de SGBDs (--sgbd-config)", self), 1, 0)
        layout.addWidget(self.sgbd_edit, 1, 1)
        layout.addWidget(sgbd_button, 1, 2)
        layout.addWidget(hint, 2, 0, 1, 3)
        layout.addWidget(self.error_label, 3, 0, 1, 3)
        layout.setColumnStretch(1, 1)

        self.config_edit.textChanged.connect(self.changed)
        self.sgbd_edit.textChanged.connect(self.changed)

    # -- reading ----------------------------------------------------------

    def config_path(self) -> Optional[Path]:
        return _as_path(self.config_edit.text())

    def sgbd_config_path(self) -> Optional[Path]:
        return _as_path(self.sgbd_edit.text())

    # -- writing ----------------------------------------------------------

    def set_paths(self, config: Optional[Path], sgbd: Optional[Path]) -> None:
        self.config_edit.setText(str(config) if config else "")
        self.sgbd_edit.setText(str(sgbd) if sgbd else "")

    def set_errors(self, errors: Dict[str, str]) -> None:
        messages = [errors[field] for field in FIELDS if field in errors]
        self.error_label.setText("  ·  ".join(messages))

    # -- internals --------------------------------------------------------

    def _browse_config(self) -> None:
        self._browse(self.config_edit, "Escolher a configuração de importação")

    def _browse_sgbd(self) -> None:
        self._browse(self.sgbd_edit, "Escolher a configuração de SGBDs")

    def _browse(self, edit: QLineEdit, title: str) -> None:
        start = edit.text() or ""
        chosen, _ = QFileDialog.getOpenFileName(self, title, start, "JSON (*.json);;Todos (*)")
        if chosen:
            edit.setText(str(Path(chosen)))


def _as_path(text: str) -> Optional[Path]:
    stripped = text.strip()
    return Path(stripped) if stripped else None
