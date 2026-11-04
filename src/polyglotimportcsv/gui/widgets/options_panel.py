"""The card holding the CLI options the GUI offers.

``--benchmark`` is deliberately absent: the GUI never benchmarks. It stays in
the CLI, where the evaluation needs it.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt
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
    QSlider,
    QWidget,
)

from polyglotimportcsv.gui.state import (
    DBMS_NAMES,
    DEFAULT_SAMPLE_SIZE,
    LOG_LEVELS,
    MAX_SAMPLE_SIZE,
)
from polyglotimportcsv.gui.widgets.info_badge import InfoBadge
from polyglotimportcsv.import_plan import DEFAULT_BATCH_LINES, MAX_BATCH_LINES, MIN_BATCH_LINES
from polyglotimportcsv.stream_source import DEFAULT_CHUNK_MB, MAX_CHUNK_MB, MIN_CHUNK_MB

SHOW_DATA_CHOICES = (
    ("sample", "Amostra (--sample)"),
    ("all", "Todos os dados (--show-data)"),
    ("none", "Nenhum dado (--no-data)"),
)
_SHOW_DATA_VALUES = {"sample": None, "all": True, "none": False}

HELP = {
    "chunk_size": (
        "Memória de cada bloco de leitura, em MB (8 a 256). A ferramenta calcula quantas "
        "linhas cabem no bloco pela largura das linhas de cada arquivo. Blocos maiores "
        "usam mais memória."
    ),
    "batch_size": (
        "Linhas por lote de gravação (1024 a 8192). O lote nunca passa das linhas de um "
        "bloco de leitura."
    ),
    "dry_run": (
        "Faz todas as verificações, inclusive a leitura dos dados, e mostra quantos "
        "registros iriam para cada destino, sem conectar a nenhum SGBD."
    ),
    "log_level": (
        "Quanto detalhe aparece no console. O arquivo de log da sessão sempre registra "
        "tudo (DEBUG)."
    ),
    "show_data": (
        "Amostra: as primeiras N linhas de cada entidade. Todos os dados: todas as "
        "linhas; lento em arquivos grandes. Nenhum dado: só as contagens."
    ),
}


class OptionsPanel(QGroupBox):
    """Checkboxes, radios, a combo and spin boxes, one per CLI option."""

    changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Opções de execução", parent)
        self.dbms_boxes = {}  # type: Dict[str, QCheckBox]
        self.show_data_buttons = {}  # type: Dict[str, QRadioButton]
        self.info_badges = {}  # type: Dict[str, InfoBadge]
        self._groups = []  # type: List[QButtonGroup]

        layout = QGridLayout(self)
        layout.addWidget(QLabel("Bancos de dados (--only)", self), 0, 0)
        layout.addLayout(self._build_dbms_row(), 0, 1)

        # Chunk size slider
        self.chunk_slider = QSlider(Qt.Orientation.Horizontal, self)

        self.chunk_slider.setRange(
            0,
            (MAX_CHUNK_MB - MIN_CHUNK_MB) / MIN_CHUNK_MB
        )
        self.chunk_slider.setSingleStep(1)
        self.chunk_slider.setPageStep(1)

        self.chunk_slider.setValue(
            DEFAULT_CHUNK_MB / MIN_CHUNK_MB
        )

        self.chunk_value_label = QLabel(self)
        self.chunk_value_label.setMinimumWidth(65)
        self.chunk_value_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.chunk_slider.valueChanged.connect(
            lambda value: self.chunk_value_label.setText(
                f"{MIN_CHUNK_MB + value * MIN_CHUNK_MB} MB"
            )
        )
        self.chunk_slider.valueChanged.connect(self.changed)

        self.chunk_value_label.setText(f"{DEFAULT_CHUNK_MB} MB")

        layout.addWidget(QLabel("Bloco lido por vez:", self), 1, 0)
        layout.addLayout(
            self._build_slider_row(
                self.chunk_slider,
                self.chunk_value_label,
                "chunk_size"
            ),
            1, 1
        )

        # Batch size slider
        self.batch_slider = QSlider(Qt.Orientation.Horizontal, self)

        self.batch_slider.setRange(
            0,
            (MAX_BATCH_LINES - MIN_BATCH_LINES) / MIN_BATCH_LINES
        )
        self.batch_slider.setSingleStep(1)
        self.batch_slider.setPageStep(1)

        self.batch_slider.setValue(
            DEFAULT_BATCH_LINES / MIN_BATCH_LINES
        )

        self.batch_value_label = QLabel(self)
        self.batch_value_label.setMinimumWidth(85)
        self.batch_value_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.batch_slider.valueChanged.connect(
            lambda value: self.batch_value_label.setText(
                f"{MIN_BATCH_LINES + value * MIN_BATCH_LINES} linhas"
            )
        )
        self.batch_slider.valueChanged.connect(self.changed)

        self.batch_value_label.setText(f"{DEFAULT_BATCH_LINES} linhas")

        layout.addWidget(QLabel("Lote gravado por vez:", self), 2, 0)
        layout.addLayout(
            self._build_slider_row(
                self.batch_slider,
                self.batch_value_label,
                "batch_size"
            ),
            2, 1
        )

        self.dry_run_box = QCheckBox("Simulação (--dry-run)", self)
        self.dry_run_box.toggled.connect(self.changed)
        modifiers = QHBoxLayout()
        modifiers.addWidget(self.dry_run_box)
        modifiers.addWidget(self._badge("dry_run"))
        modifiers.addStretch(1)
        layout.addWidget(QLabel("Modificadores", self), 3, 0)
        layout.addLayout(modifiers, 3, 1)

        self.log_combo = QComboBox(self)
        self.log_combo.addItems(list(LOG_LEVELS))
        self.log_combo.setCurrentText("INFO")
        self.log_combo.currentTextChanged.connect(self.changed)
        log_row = QHBoxLayout()
        log_row.addWidget(self.log_combo)
        log_row.addWidget(self._badge("log_level"))
        log_row.addStretch(1)
        layout.addWidget(QLabel("Nível de log (--log-level)", self), 4, 0)
        layout.addLayout(log_row, 4, 1)

        layout.addWidget(QLabel("Exibição de dados", self), 5, 0)
        layout.addLayout(self._build_show_data_row(), 5, 1)

        self.error_label = QLabel("", self)
        self.error_label.setObjectName("errorLabel")
        layout.addWidget(self.error_label, 6, 0, 1, 2)
        layout.setColumnStretch(1, 1)

    # -- reading ----------------------------------------------------------

    def only(self) -> Tuple[str, ...]:
        return tuple(name for name in DBMS_NAMES if self.dbms_boxes[name].isChecked())

    def chunk_size_mb(self) -> int:
        return MIN_CHUNK_MB + self.chunk_slider.value() * MIN_CHUNK_MB

    def batch_size(self) -> int:
        return MIN_BATCH_LINES + self.batch_slider.value() * MIN_BATCH_LINES

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
        keys = ("only", "chunk_size_mb", "batch_size", "sample_size")
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

    def _build_slider_row(
        self,
        slider: QSlider,
        value_label: QLabel,
        help_key: str
    ) -> QHBoxLayout:
        row = QHBoxLayout()

        slider.setMinimumWidth(300)
        row.addWidget(slider)
        row.addWidget(value_label)
        row.addWidget(self._badge(help_key))
        row.addStretch(1)

        return row

    def _build_show_data_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        group = QButtonGroup(self)
        self._groups.append(group)
        self.sample_spin = QSpinBox(self)
        self.sample_spin.setRange(1, MAX_SAMPLE_SIZE)
        self.sample_spin.setValue(DEFAULT_SAMPLE_SIZE)
        self.sample_spin.setToolTip("Linhas mostradas por entidade (--sample N)")
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
