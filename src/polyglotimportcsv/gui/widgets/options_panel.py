"""The card holding every execution option of the CLI."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QWidget,
)

from polyglotimportcsv.gui.state import DBMS_NAMES, EXECUTIONS, LOG_LEVELS, STRATEGIES

SHOW_DATA_CHOICES = (
    ("auto", "Automático"),
    ("always", "Sempre (--show-data)"),
    ("never", "Nunca (--no-data)"),
)


class OptionsPanel(QGroupBox):
    """Checkboxes, radios and a combo, one per CLI option."""

    changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Opções de execução", parent)
        self.dbms_boxes = {}  # type: Dict[str, QCheckBox]
        self.strategy_buttons = {}  # type: Dict[str, QRadioButton]
        self.execution_buttons = {}  # type: Dict[str, QRadioButton]
        self.show_data_buttons = {}  # type: Dict[str, QRadioButton]
        self._groups = []  # type: List[QButtonGroup]

        layout = QGridLayout(self)
        layout.addWidget(QLabel("Bancos de dados (--only)", self), 0, 0)
        layout.addLayout(self._build_dbms_row(), 0, 1)
        layout.addWidget(QLabel("Estratégia (--strategy)", self), 1, 0)
        layout.addLayout(self._build_radio_row(STRATEGIES, self.strategy_buttons, "optimized"), 1, 1)
        layout.addWidget(QLabel("Execução (--execution)", self), 2, 0)
        layout.addLayout(self._build_radio_row(EXECUTIONS, self.execution_buttons, "stream"), 2, 1)

        self.dry_run_box = QCheckBox("Simulação (--dry-run)", self)
        self.create_schema_box = QCheckBox("Criar esquema (--create-schema)", self)
        self.create_schema_box.setChecked(True)
        self.benchmark_box = QCheckBox("Benchmark (--benchmark)", self)
        modifiers = QHBoxLayout()
        for box in (self.dry_run_box, self.create_schema_box, self.benchmark_box):
            box.toggled.connect(self.changed)
            modifiers.addWidget(box)
        modifiers.addStretch(1)
        layout.addWidget(QLabel("Modificadores", self), 3, 0)
        layout.addLayout(modifiers, 3, 1)

        self.log_combo = QComboBox(self)
        self.log_combo.addItems(list(LOG_LEVELS))
        self.log_combo.setCurrentText("INFO")
        self.log_combo.currentTextChanged.connect(self.changed)
        bottom = QHBoxLayout()
        bottom.addWidget(self.log_combo)
        bottom.addSpacing(18)
        bottom.addWidget(QLabel("Exibição de dados", self))
        group = QButtonGroup(self)
        self._groups.append(group)
        for key, label in SHOW_DATA_CHOICES:
            button = QRadioButton(label, self)
            button.setChecked(key == "auto")
            button.toggled.connect(self._on_radio_toggled)
            group.addButton(button)
            self.show_data_buttons[key] = button
            bottom.addWidget(button)
        bottom.addStretch(1)
        layout.addWidget(QLabel("Nível de log (--log-level)", self), 4, 0)
        layout.addLayout(bottom, 4, 1)

        self.error_label = QLabel("", self)
        self.error_label.setObjectName("errorLabel")
        layout.addWidget(self.error_label, 5, 0, 1, 2)
        layout.setColumnStretch(1, 1)

    # -- reading ----------------------------------------------------------

    def only(self) -> Tuple[str, ...]:
        return tuple(name for name in DBMS_NAMES if self.dbms_boxes[name].isChecked())

    def strategy(self) -> str:
        return self._selected(self.strategy_buttons, "optimized")

    def execution(self) -> str:
        return self._selected(self.execution_buttons, "stream")

    def dry_run(self) -> bool:
        return self.dry_run_box.isChecked()

    def create_schema(self) -> bool:
        return self.create_schema_box.isChecked()

    def benchmark(self) -> bool:
        return self.benchmark_box.isChecked()

    def log_level(self) -> str:
        return self.log_combo.currentText()

    def show_data(self) -> Optional[bool]:
        key = self._selected(self.show_data_buttons, "auto")
        return {"auto": None, "always": True, "never": False}[key]

    # -- writing ----------------------------------------------------------

    def set_available_dbms(self, names: Optional[Sequence[str]]) -> None:
        """Restrict the checkboxes to ``names``; ``None`` re-enables them all."""
        for name, box in self.dbms_boxes.items():
            enabled = names is None or name in names
            box.setEnabled(enabled)
            if not enabled and box.isChecked():
                box.setChecked(False)

    def set_errors(self, errors: Dict[str, str]) -> None:
        self.error_label.setText(errors.get("only", ""))

    # -- internals --------------------------------------------------------

    def _build_dbms_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        for name in DBMS_NAMES:
            box = QCheckBox(name, self)
            box.toggled.connect(self.changed)
            self.dbms_boxes[name] = box
            row.addWidget(box)
        row.addStretch(1)
        return row

    def _build_radio_row(self, values, target, default) -> QHBoxLayout:
        row = QHBoxLayout()
        group = QButtonGroup(self)
        self._groups.append(group)
        for value in values:
            button = QRadioButton(value, self)
            button.setChecked(value == default)
            button.toggled.connect(self._on_radio_toggled)
            group.addButton(button)
            target[value] = button
            row.addWidget(button)
        row.addStretch(1)
        return row

    def _on_radio_toggled(self, checked: bool) -> None:
        if checked:
            self.changed.emit()

    @staticmethod
    def _selected(buttons: Dict[str, QRadioButton], default: str) -> str:
        for key, button in buttons.items():
            if button.isChecked():
                return key
        return default
