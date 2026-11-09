"""The card holding the CLI options the GUI offers.

``--benchmark`` is deliberately absent: the GUI never benchmarks. It stays in
the CLI, where the evaluation needs it.
"""

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
    QSpinBox,
    QWidget,
)

from polyglotimportcsv.gui.state import (
    DBMS_NAMES,
    DEFAULT_SAMPLE_SIZE,
    LOG_LEVELS,
    MAX_SAMPLE_SIZE,
)
from polyglotimportcsv.gui.widgets.info_badge import InfoBadge

SHOW_DATA_CHOICES = (
    ("sample", "Sample (--sample)"),
    ("all", "All rows (--show-data)"),
    ("none", "No data (--no-data)"),
)
_SHOW_DATA_VALUES = {"sample": None, "all": True, "none": False}

HELP = {
    "dry_run": (
        "Runs every check, including the read of the data rows, and shows how many "
        "records would go to each target, without connecting to any DBMS."
    ),
    "log_level": (
        "How much detail the console shows. The session log file always records "
        "everything (DEBUG)."
    ),
    "show_data": (
        "Sample: the first N rows of each entity. All rows: every row; slow on large "
        "files. No data: only the counts."
    ),
}


class OptionsPanel(QGroupBox):
    """Checkboxes, radios, a combo and a spin box, one per CLI option the GUI sets.

    The read block and the write batch have none: the CLI chooses them.
    """

    changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Run options", parent)
        self.dbms_boxes = {}  # type: Dict[str, QCheckBox]
        self.show_data_buttons = {}  # type: Dict[str, QRadioButton]
        self.info_badges = {}  # type: Dict[str, InfoBadge]
        self._groups = []  # type: List[QButtonGroup]

        layout = QGridLayout(self)
        layout.addWidget(QLabel("Databases (--only)", self), 0, 0)
        layout.addLayout(self._build_dbms_row(), 0, 1)

        self.dry_run_box = QCheckBox("Dry run (--dry-run)", self)
        self.dry_run_box.toggled.connect(self.changed)
        modifiers = QHBoxLayout()
        modifiers.addWidget(self.dry_run_box)
        modifiers.addWidget(self._badge("dry_run"))
        modifiers.addStretch(1)
        layout.addWidget(QLabel("Modifiers", self), 1, 0)
        layout.addLayout(modifiers, 1, 1)

        self.log_combo = QComboBox(self)
        self.log_combo.addItems(list(LOG_LEVELS))
        self.log_combo.setCurrentText("INFO")
        self.log_combo.currentTextChanged.connect(self.changed)
        log_row = QHBoxLayout()
        log_row.addWidget(self.log_combo)
        log_row.addWidget(self._badge("log_level"))
        log_row.addStretch(1)
        layout.addWidget(QLabel("Log level (--log-level)", self), 2, 0)
        layout.addLayout(log_row, 2, 1)

        layout.addWidget(QLabel("Data display", self), 3, 0)
        layout.addLayout(self._build_show_data_row(), 3, 1)

        self.error_label = QLabel("", self)
        self.error_label.setObjectName("errorLabel")
        layout.addWidget(self.error_label, 4, 0, 1, 2)
        layout.setColumnStretch(1, 1)

    # -- reading ----------------------------------------------------------

    def only(self) -> Tuple[str, ...]:
        return tuple(name for name in DBMS_NAMES if self.dbms_boxes[name].isChecked())

    def dry_run(self) -> bool:
        return self.dry_run_box.isChecked()

    def log_level(self) -> str:
        return self.log_combo.currentText()

    def show_data(self) -> Optional[bool]:
        return _SHOW_DATA_VALUES[self._selected(self.show_data_buttons, "sample")]

    def sample_size(self) -> int:
        return self.sample_spin.value()

    # -- writing ----------------------------------------------------------

    def set_available_dbms(self, names: Optional[Sequence[str]]) -> None:
        """Restrict the checkboxes to ``names``; ``None`` re-enables them all."""
        for name, box in self.dbms_boxes.items():
            enabled = names is None or name in names
            box.setEnabled(enabled)
            if not enabled and box.isChecked():
                box.setChecked(False)

    def set_errors(self, errors: Dict[str, str]) -> None:
        keys = ("only", "sample_size")
        messages = [errors[key] for key in keys if key in errors]
        self.error_label.setText("  ·  ".join(messages))

    # -- internals --------------------------------------------------------

    def _badge(self, key: str) -> InfoBadge:
        badge = InfoBadge(HELP[key], self)
        self.info_badges[key] = badge
        return badge

    def _build_dbms_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        for name in DBMS_NAMES:
            box = QCheckBox(name, self)
            box.toggled.connect(self.changed)
            self.dbms_boxes[name] = box
            row.addWidget(box)
        row.addStretch(1)
        return row

    def _build_show_data_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        group = QButtonGroup(self)
        self._groups.append(group)
        self.sample_spin = QSpinBox(self)
        self.sample_spin.setRange(1, MAX_SAMPLE_SIZE)
        self.sample_spin.setValue(DEFAULT_SAMPLE_SIZE)
        self.sample_spin.setToolTip("Rows shown per entity (--sample N)")
        self.sample_spin.valueChanged.connect(self.changed)
        for key, label in SHOW_DATA_CHOICES:
            button = QRadioButton(label, self)
            button.setChecked(key == "sample")
            button.toggled.connect(self._on_radio_toggled)
            group.addButton(button)
            self.show_data_buttons[key] = button
            row.addWidget(button)
            if key == "sample":
                row.addWidget(self.sample_spin)
            row.addSpacing(8)
        row.addWidget(self._badge("show_data"))
        row.addStretch(1)
        self.show_data_buttons["sample"].toggled.connect(self.sample_spin.setEnabled)
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
