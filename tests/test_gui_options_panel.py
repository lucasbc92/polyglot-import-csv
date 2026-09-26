"""Every CLI flag that is a checkbox, radio or combo."""

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from polyglotimportcsv.gui.state import DBMS_NAMES  # noqa: E402
from polyglotimportcsv.gui.widgets.options_panel import OptionsPanel  # noqa: E402


def test_defaults_match_the_cli(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    assert panel.only() == ()
    assert panel.execution() == "stream"
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


def test_execution_radios(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    panel.execution_buttons["materialize"].setChecked(True)
    assert panel.execution() == "materialize"


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
        "stream", "materialize", "dry_run", "create_schema", "log_level", "show_data",
    }
    assert "memória" in panel.info_badges["stream"].toolTip()
    assert "lento" in panel.info_badges["show_data"].toolTip()


def test_sample_size_errors_are_shown(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    panel.set_errors({"sample_size": "O tamanho da amostra deve estar entre 1 e 1000000."})
    assert "amostra" in panel.error_label.text()


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
