"""The card holding every execution option of the CLI the GUI offers.

``--strategy`` and ``--benchmark`` are deliberately absent: the GUI always
writes with ``optimized`` and never benchmarks. Both stay in the CLI, where the
evaluation needs them.
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
    EXECUTIONS,
    LOG_LEVELS,
    MAX_SAMPLE_SIZE,
)
from polyglotimportcsv.gui.widgets.info_badge import InfoBadge

SHOW_DATA_CHOICES = (
    ("sample", "Amostra (--sample)"),
    ("all", "Todos os dados (--show-data)"),
    ("none", "Nenhum dado (--no-data)"),
)
_SHOW_DATA_VALUES = {"sample": None, "all": True, "none": False}

HELP = {
    "stream": (
        "Importa em fluxo: lê cada CSV em blocos e grava bloco a bloco. A memória "
        "usada não cresce com o tamanho do arquivo. É o modo recomendado."
    ),
    "materialize": (
        "Carrega cada fonte inteira na memória, monta todas as entidades e só então "
        "grava. Útil para inspecionar os dados; exige memória proporcional ao arquivo."
    ),
    "dry_run": (
        "Valida as configurações e mostra quantos registros iriam para cada destino, "
        "sem conectar a nenhum SGBD. Usa sempre a materialização."
    ),
    "create_schema": (
        "Cria tabelas, coleções, keyspace e índices que ainda não existirem antes de gravar."
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
    """Checkboxes, radios, a combo and a spin box, one per CLI option."""

    changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Opções de execução", parent)
        self.dbms_boxes = {}  # type: Dict[str, QCheckBox]
        self.execution_buttons = {}  # type: Dict[str, QRadioButton]
        self.show_data_buttons = {}  # type: Dict[str, QRadioButton]
        self.info_badges = {}  # type: Dict[str, InfoBadge]
        self._groups = []  # type: List[QButtonGroup]

        layout = QGridLayout(self)
        layout.addWidget(QLabel("Bancos de dados (--only)", self), 0, 0)
        layout.addLayout(self._build_dbms_row(), 0, 1)
        layout.addWidget(QLabel("Execução (--execution)", self), 1, 0)
        layout.addLayout(self._build_execution_row(), 1, 1)

        self.dry_run_box = QCheckBox("Simulação (--dry-run)", self)
        self.create_schema_box = QCheckBox("Criar esquema (--create-schema)", self)
        self.create_schema_box.setChecked(True)
        modifiers = QHBoxLayout()
        for key, box in (("dry_run", self.dry_run_box), ("create_schema", self.create_schema_box)):
            box.toggled.connect(self.changed)
            modifiers.addWidget(box)
            modifiers.addWidget(self._badge(key))
            modifiers.addSpacing(12)
        modifiers.addStretch(1)
        layout.addWidget(QLabel("Modificadores", self), 2, 0)
        layout.addLayout(modifiers, 2, 1)

        self.log_combo = QComboBox(self)
        self.log_combo.addItems(list(LOG_LEVELS))
        self.log_combo.setCurrentText("INFO")
        self.log_combo.currentTextChanged.connect(self.changed)
        log_row = QHBoxLayout()
        log_row.addWidget(self.log_combo)
        log_row.addWidget(self._badge("log_level"))
        log_row.addStretch(1)
        layout.addWidget(QLabel("Nível de log (--log-level)", self), 3, 0)
        layout.addLayout(log_row, 3, 1)

        layout.addWidget(QLabel("Exibição de dados", self), 4, 0)
        layout.addLayout(self._build_show_data_row(), 4, 1)

        self.error_label = QLabel("", self)
        self.error_label.setObjectName("errorLabel")
        layout.addWidget(self.error_label, 5, 0, 1, 2)
        layout.setColumnStretch(1, 1)

    # -- reading ----------------------------------------------------------

    def only(self) -> Tuple[str, ...]:
        return tuple(name for name in DBMS_NAMES if self.dbms_boxes[name].isChecked())

    def execution(self) -> str:
        return self._selected(self.execution_buttons, "stream")

    def dry_run(self) -> bool:
        return self.dry_run_box.isChecked()

    def create_schema(self) -> bool:
        return self.create_schema_box.isChecked()

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
        messages = [errors[key] for key in ("only", "sample_size") if key in errors]
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

    def _build_execution_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        group = QButtonGroup(self)
        self._groups.append(group)
        for value in EXECUTIONS:
            button = QRadioButton(value, self)
            button.setChecked(value == "stream")
            button.toggled.connect(self._on_radio_toggled)
            group.addButton(button)
            self.execution_buttons[value] = button
            row.addWidget(button)
            row.addWidget(self._badge(value))
            row.addSpacing(12)
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
