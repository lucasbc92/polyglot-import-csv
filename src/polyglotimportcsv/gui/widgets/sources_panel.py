"""The card holding the repeatable --source NAME=PATH overrides."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

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
    "da configuração de importação. O nome de cada fonte é deduzido do arquivo "
    "escolhido e pode ser corrigido na tabela."
)
CSV_FILTER = "CSV (*.csv);;Todos (*)"


class SourcesPanel(QGroupBox):
    """A two-column table of source name and CSV path.

    Rows are created by choosing files, never by hand: an override is a path,
    and a row with no path in it is not one. Adding a blank row and using that
    row to summon the file dialog made the dialog a second, hidden step behind
    a cell that looked like somewhere to type.
    """

    changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Fontes CSV — sobrescrita de caminhos (--source)", parent)
        #: {declared name: declared file name} from the import configuration,
        #: or None while it is unknown. Used to name a chosen file the way the
        #: configuration does; see _name_for.
        self._known = None  # type: Optional[Dict[str, str]]

        self.table = QTableWidget(0, 2, self)
        self.table.setHorizontalHeaderLabels(["Nome da fonte", "Arquivo CSV"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemDoubleClicked.connect(self._on_double_click)

        # Injection points for the two dialogs, so the panel can be driven in
        # tests without a modal window ever opening. Same device as
        # ConsolePanel.confirm_discard.
        self.choose_files = self._ask_for_files
        self.choose_folder = self._ask_for_folder

        self.add_button = QPushButton("+ Adicionar arquivos", self)
        self.add_button.setToolTip("Escolher um ou mais arquivos CSV")
        self.add_folder_button = QPushButton("+ Adicionar pasta", self)
        self.add_folder_button.setToolTip(
            "Anexar de uma vez todos os arquivos .csv de uma pasta"
        )
        self.remove_button = QPushButton("− Remover", self)
        self.add_button.clicked.connect(self.add_files)
        self.add_folder_button.clicked.connect(self.add_folder)
        self.remove_button.clicked.connect(self.remove_selected_rows)

        self.error_label = QLabel("", self)
        self.error_label.setObjectName("errorLabel")
        hint = QLabel(HINT, self)
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)

        buttons = QHBoxLayout()
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.add_folder_button)
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

    def paths(self) -> Tuple[str, ...]:
        """The path cell of every row, for skipping files already listed."""
        return tuple(self._cell(index, 1) for index in range(self.table.rowCount()))

    # -- writing ----------------------------------------------------------

    def add_files(self) -> int:
        """Ask for CSV files and append a row per file. Returns rows added."""
        chosen = self.choose_files()
        return self.attach([Path(path) for path in chosen])

    def add_folder(self) -> int:
        """Ask for a folder and append a row per ``.csv`` directly inside it."""
        folder = self.choose_folder()
        if not folder:
            return 0
        # Not recursive, and sorted so the rows land in a predictable order
        # rather than in whatever order the filesystem reports.
        found = sorted(
            (entry for entry in Path(folder).glob("*") if entry.suffix.lower() == ".csv"),
            key=lambda entry: entry.name.lower(),
        )
        return self.attach(found)

    def attach(self, paths: Iterable[Path]) -> int:
        """Append a row per path, skipping those already in the table.

        Emits ``changed`` once for the whole batch: a folder of twenty files
        would otherwise rebuild the command twenty times.
        """
        listed = set(self.paths())
        pending = []  # type: List[Tuple[str, str]]
        for path in paths:
            text = str(path)
            if text in listed:
                continue
            listed.add(text)
            pending.append((self._name_for(path), text))
        if not pending:
            return 0
        self.table.blockSignals(True)
        try:
            for name, text in pending:
                index = self.table.rowCount()
                self.table.insertRow(index)
                self.table.setItem(index, 0, QTableWidgetItem(name))
                self.table.setItem(index, 1, QTableWidgetItem(text))
        finally:
            self.table.blockSignals(False)
        self.changed.emit()
        return len(pending)

    def add_row(self, name: str = "", path: str = "") -> int:
        """Append one row verbatim, without consulting the configuration."""
        index = self.table.rowCount()
        self.table.blockSignals(True)
        try:
            self.table.insertRow(index)
            self.table.setItem(index, 0, QTableWidgetItem(name))
            self.table.setItem(index, 1, QTableWidgetItem(path))
        finally:
            self.table.blockSignals(False)
        self.changed.emit()
        return index

    def remove_selected_rows(self) -> None:
        indexes = sorted({item.row() for item in self.table.selectedItems()}, reverse=True)
        if not indexes:
            return
        self.table.blockSignals(True)
        try:
            for index in indexes:
                self.table.removeRow(index)
        finally:
            self.table.blockSignals(False)
        self.changed.emit()

    def set_known_sources(self, sources: Optional[Dict[str, str]]) -> None:
        """Record ``{declared name: declared file name}`` from the config."""
        self._known = dict(sources) if sources else None

    def set_errors(self, errors: Dict[str, str]) -> None:
        self.error_label.setText(errors.get("sources", ""))

    # -- internals --------------------------------------------------------

    def _name_for(self, path: Path) -> str:
        """The source name a chosen file most likely overrides.

        ``--source`` keys a path to a source *declared in the configuration*,
        so the file's own stem is usually the wrong answer: the reference
        dataset declares ``stock`` and stores it in ``ecommerce_stock.csv``,
        and a row saying ``ecommerce_stock`` would be rejected by the CLI as an
        unknown source. The declared file name is therefore tried first, then
        the declared names themselves, and only then the stem.
        """
        if not self._known:
            return path.stem
        target = path.name.lower()
        for name, declared in self._known.items():
            if declared and Path(declared).name.lower() == target:
                return name
        stem = path.stem.lower()
        matches = [name for name in self._known if name.lower() == stem]
        if matches:
            return matches[0]
        # Longest suffix wins, so a dataset declaring both "stock" and
        # "restock" cannot have "ecommerce_restock.csv" claimed by "stock".
        suffixed = [name for name in self._known if stem.endswith("_" + name.lower())]
        if suffixed:
            return max(suffixed, key=len)
        return path.stem

    def _start_directory(self) -> str:
        """Where a dialog should open: next to the last file already listed."""
        for text in reversed(self.paths()):
            if text:
                return str(Path(text).parent)
        return ""

    def _ask_for_files(self) -> Sequence[str]:
        chosen, _ = QFileDialog.getOpenFileNames(
            self, "Escolher arquivos CSV", self._start_directory(), CSV_FILTER
        )
        return chosen

    def _ask_for_folder(self) -> str:
        return QFileDialog.getExistingDirectory(
            self, "Escolher a pasta com os arquivos CSV", self._start_directory()
        )

    def _cell(self, row: int, column: int) -> str:
        item = self.table.item(row, column)
        return item.text().strip() if item is not None else ""

    def _on_item_changed(self, _item: QTableWidgetItem) -> None:
        self.changed.emit()

    def _on_double_click(self, item: QTableWidgetItem) -> None:
        if item.column() != 1:
            return
        chosen, _ = QFileDialog.getOpenFileName(
            self, "Escolher o arquivo CSV", item.text(), CSV_FILTER
        )
        if chosen:
            item.setText(str(Path(chosen)))
