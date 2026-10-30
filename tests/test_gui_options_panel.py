"""Every CLI flag that is a checkbox, radio, combo or spin box."""

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from PySide6.QtWidgets import QLabel, QRadioButton  # noqa: E402

from polyglotimportcsv.gui.state import DBMS_NAMES  # noqa: E402
from polyglotimportcsv.gui.widgets.options_panel import OptionsPanel  # noqa: E402


def test_defaults_match_the_cli(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    assert panel.only() == ()
    assert panel.chunk_size_mb() == 8
    assert panel.batch_size() == 1024
    assert panel.dry_run() is False
    assert panel.create_schema() is True
    assert panel.log_level() == "INFO"
    assert panel.show_data() is None
    assert panel.sample_size() == 50


def test_every_dbms_has_a_checkbox(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    assert tuple(panel.dbms_boxes.keys()) == DBMS_NAMES


def test_checking_dbms_boxes_keeps_cli_order(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    panel.dbms_boxes["mongodb"].setChecked(True)
    panel.dbms_boxes["postgres"].setChecked(True)
    assert panel.only() == ("postgres", "mongodb")


def test_changing_a_control_emits_changed(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    with qtbot.waitSignal(panel.changed, timeout=1000):
        panel.dbms_boxes["redis"].setChecked(True)


def test_strategy_and_benchmark_are_gone(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    assert not hasattr(panel, "strategy_buttons")
    assert not hasattr(panel, "benchmark_box")


def test_options_panel_has_two_size_spins_and_only_the_data_radios(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    # The only radios left are the three ways of showing data.
    assert {button.text() for button in panel.findChildren(QRadioButton)} == {
        "Amostra (--sample)", "Todos os dados (--show-data)", "Nenhum dado (--no-data)",
    }
    flag_labels = {label.text() for label in panel.findChildren(QLabel) if "(--" in label.text()}
    assert flag_labels == {
        "Bancos de dados (--only)",
        "Bloco em MB (--chunk-size)",
        "Lote (--batch-size)",
        "Nível de log (--log-level)",
    }
    assert (panel.chunk_spin.minimum(), panel.chunk_spin.maximum()) == (8, 256)
    assert panel.chunk_spin.value() == 8
    assert (panel.batch_spin.minimum(), panel.batch_spin.maximum()) == (1024, 8192)
    assert panel.batch_spin.value() == 1024
    assert panel.batch_spin.singleStep() == 1024


def test_the_size_readers_follow_the_spin_boxes(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    panel.chunk_spin.setValue(64)
    panel.batch_spin.setValue(4096)
    assert panel.chunk_size_mb() == 64
    assert panel.batch_size() == 4096


def test_the_batch_arrows_step_by_1024(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    panel.batch_spin.stepUp()
    assert panel.batch_size() == 2048


@pytest.mark.parametrize("spin", ["chunk_spin", "batch_spin"])
def test_changing_a_size_emits_changed(qtbot, spin):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    with qtbot.waitSignal(panel.changed, timeout=1000):
        getattr(panel, spin).stepUp()


def test_data_display_modes_and_labels(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    assert panel.show_data_buttons["sample"].text() == "Amostra (--sample)"
    assert panel.show_data_buttons["all"].text() == "Todos os dados (--show-data)"
    assert panel.show_data_buttons["none"].text() == "Nenhum dado (--no-data)"
    panel.show_data_buttons["all"].setChecked(True)
    assert panel.show_data() is True
    panel.show_data_buttons["none"].setChecked(True)
    assert panel.show_data() is False
    panel.show_data_buttons["sample"].setChecked(True)
    assert panel.show_data() is None


def test_the_sample_size_is_only_editable_while_sampling(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    assert panel.sample_spin.isEnabled()
    panel.show_data_buttons["all"].setChecked(True)
    assert not panel.sample_spin.isEnabled()
    panel.show_data_buttons["sample"].setChecked(True)
    assert panel.sample_spin.isEnabled()


def test_changing_the_sample_size_emits_changed(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    with qtbot.waitSignal(panel.changed, timeout=1000):
        panel.sample_spin.setValue(120)
    assert panel.sample_size() == 120


def test_the_sample_size_range(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    assert panel.sample_spin.minimum() == 1
    assert panel.sample_spin.maximum() == 1000000


def test_every_unclear_option_has_a_help_badge(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    assert set(panel.info_badges) == {
        "chunk_size", "batch_size", "dry_run", "create_schema", "log_level", "show_data",
    }
    assert panel.info_badges["chunk_size"].toolTip() == (
        "Memória de cada bloco de leitura, em MB (8 a 256). A ferramenta calcula quantas "
        "linhas cabem no bloco pela largura das linhas de cada arquivo. Blocos maiores "
        "usam mais memória."
    )
    assert panel.info_badges["batch_size"].toolTip() == (
        "Linhas por lote de gravação (1024 a 8192). O lote nunca passa das linhas de um "
        "bloco de leitura."
    )
    assert panel.info_badges["dry_run"].toolTip() == (
        "Faz todas as verificações, inclusive a leitura dos dados, e mostra quantos "
        "registros iriam para cada destino, sem conectar a nenhum SGBD."
    )
    assert "lento" in panel.info_badges["show_data"].toolTip()


def test_sample_size_errors_are_shown(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    panel.set_errors({"sample_size": "O tamanho da amostra deve estar entre 1 e 1000000."})
    assert "amostra" in panel.error_label.text()


def test_size_errors_are_shown(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    panel.set_errors({
        "chunk_size_mb": "O bloco deve ter entre 8 e 256 MB.",
        "batch_size": "O lote deve ter entre 1024 e 8192 linhas.",
    })
    assert "O bloco deve ter entre 8 e 256 MB." in panel.error_label.text()
    assert "O lote deve ter entre 1024 e 8192 linhas." in panel.error_label.text()


def test_log_level_combo(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    panel.log_combo.setCurrentText("DEBUG")
    assert panel.log_level() == "DEBUG"


def test_available_dbms_disables_the_others(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    panel.set_available_dbms(["postgres", "redis"])
    assert panel.dbms_boxes["postgres"].isEnabled()
    assert not panel.dbms_boxes["neo4j"].isEnabled()


def test_disabling_a_checked_dbms_unchecks_it(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    panel.dbms_boxes["neo4j"].setChecked(True)
    panel.set_available_dbms(["postgres"])
    assert panel.only() == ()


def test_none_reenables_every_dbms(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    panel.set_available_dbms(["postgres"])
    panel.set_available_dbms(None)
    assert all(box.isEnabled() for box in panel.dbms_boxes.values())
