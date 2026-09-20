"""The card holding the repeatable --source NAME=PATH overrides."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

HINT = (
    "Deixe a tabela vazia para usar os caminhos declarados no bloco \"sources\" "
    "da configuração de importação."
)


class SourcesPanel(QGroupBox):
    """A two-column table of source name and CSV path."""

    changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Fontes CSV — sobrescrita de caminhos (--source)", parent)
        self.table = QTableWidget(0, 2, self)
        self.table.setHorizontalHeaderLabels(["Nome da fonte", "Arquivo CSV"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemDoubleClicked.connect(self._on_double_click)

        self.add_button = QPushButton("+ Adicionar fonte", self)
        self.remove_button = QPushButton("− Remover", self)
        self.add_button.clicked.connect(lambda: self.add_row())
        self.remove_button.clicked.connect(self.remove_selected_rows)

        self.error_label = QLabel("", self)
        self.error_label.setObjectName("errorLabel")
        hint = QLabel(HINT, self)
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)

        buttons = QHBoxLayout()
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(buttons)
        layout.addWidget(self.table)
        layout.addWidget(hint)
        layout.addWidget(self.error_label)

    # -- reading ----------------------------------------------------------

    def sources(self) -> Tuple[Tuple[str, Path], ...]:
        """Return every row that is not entirely blank."""
        rows = []
        for index in range(self.table.rowCount()):
            name = self._cell(index, 0)
            path = self._cell(index, 1)
            if not name and not path:
                continue
            rows.append((name, Path(path)))
        return tuple(rows)

    # -- writing ----------------------------------------------------------

    def add_row(self, name: str = "", path: str = "") -> int:
        index = self.table.rowCount()
        self.table.blockSignals(True)
        self.table.insertRow(index)
        self.table.setItem(index, 0, QTableWidgetItem(name))
        self.table.setItem(index, 1, QTableWidgetItem(path))
        self.table.blockSignals(False)
        self.changed.emit()
        return index

    def remove_selected_rows(self) -> None:
        indexes = sorted({item.row() for item in self.table.selectedItems()}, reverse=True)
        if not indexes:
            return
        self.table.blockSignals(True)
        for index in indexes:
            self.table.removeRow(index)
        self.table.blockSignals(False)
        self.changed.emit()

    def set_errors(self, errors: Dict[str, str]) -> None:
        self.error_label.setText(errors.get("sources", ""))

    # -- internals --------------------------------------------------------

    def _cell(self, row: int, column: int) -> str:
        item = self.table.item(row, column)
        return item.text().strip() if item is not None else ""

    def _on_item_changed(self, _item: QTableWidgetItem) -> None:
        self.changed.emit()

    def _on_double_click(self, item: QTableWidgetItem) -> None:
        if item.column() != 1:
            return
        chosen, _ = QFileDialog.getOpenFileName(
            self, "Escolher o arquivo CSV", item.text(), "CSV (*.csv);;Todos (*)"
        )
        if chosen:
            item.setText(str(Path(chosen)))
