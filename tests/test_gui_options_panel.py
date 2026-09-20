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
    assert panel.strategy() == "optimized"
    assert panel.execution() == "stream"
    assert panel.dry_run() is False
    assert panel.create_schema() is True
    assert panel.benchmark() is False
    assert panel.log_level() == "INFO"
    assert panel.show_data() is None


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


def test_strategy_and_execution_radios(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    panel.strategy_buttons["naive"].setChecked(True)
    panel.execution_buttons["materialize"].setChecked(True)
    assert panel.strategy() == "naive"
    assert panel.execution() == "materialize"


def test_show_data_tri_state(qtbot):
    panel = OptionsPanel()
    qtbot.addWidget(panel)
    panel.show_data_buttons["always"].setChecked(True)
    assert panel.show_data() is True
    panel.show_data_buttons["never"].setChecked(True)
    assert panel.show_data() is False
    panel.show_data_buttons["auto"].setChecked(True)
    assert panel.show_data() is None


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
