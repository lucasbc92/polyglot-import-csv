"""Every CLI flag that is a checkbox, radio, combo or spin box."""

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from PySide6.QtWidgets import QLabel, QRadioButton, QSlider, QSpinBox  # noqa: E402

from polyglotimportcsv.gui.state import DBMS_NAMES  # noqa: E402
from polyglotimportcsv.gui.widgets.options_panel import OptionsPanel  # noqa: E402


def test_defaults_match_the_cli(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    assert panel.only() == ()
    assert panel.dry_run() is False
    assert not hasattr(panel, "create_schema_box")
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


def test_options_panel_has_no_size_controls(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    # The read block and the write batch are automatic: no control sets them.
    assert panel.findChildren(QSlider) == []
    assert panel.findChildren(QSpinBox) == [panel.sample_spin]
    for name in ("chunk_slider", "batch_slider", "chunk_size_mb", "batch_size"):
        assert not hasattr(panel, name)
    # The only radios left are the three ways of showing data.
    assert {button.text() for button in panel.findChildren(QRadioButton)} == {
        "Sample (--sample)", "All rows (--show-data)", "No data (--no-data)",
    }
    flag_labels = {label.text() for label in panel.findChildren(QLabel) if "(--" in label.text()}
    assert flag_labels == {"Databases (--only)", "Log level (--log-level)"}


def test_data_display_modes_and_labels(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    assert panel.show_data_buttons["sample"].text() == "Sample (--sample)"
    assert panel.show_data_buttons["all"].text() == "All rows (--show-data)"
    assert panel.show_data_buttons["none"].text() == "No data (--no-data)"
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
        "dry_run", "log_level", "show_data",
    }
    assert panel.info_badges["dry_run"].toolTip() == (
        "Runs every check, including the read of the data rows, and shows how many "
        "records would go to each target, without connecting to any DBMS."
    )
    assert "slow" in panel.info_badges["show_data"].toolTip()


def test_sample_size_errors_are_shown(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    panel.set_errors({"sample_size": "The sample size must be between 1 and 1000000."})
    assert "sample size" in panel.error_label.text()


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
