"""The two file-chooser rows."""

from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from polyglotimportcsv.gui.widgets.config_panel import ConfigPanel  # noqa: E402


def test_starts_empty(qtbot):
    panel = ConfigPanel()
    qtbot.addWidget(panel)
    assert panel.config_path() is None
    assert panel.sgbd_config_path() is None


def test_typing_a_path_emits_changed(qtbot):
    panel = ConfigPanel()
    qtbot.addWidget(panel)
    with qtbot.waitSignal(panel.changed, timeout=1000):
        panel.config_edit.setText("/proj/import_config.json")
    assert panel.config_path() == Path("/proj/import_config.json")


def test_set_paths_populates_both_fields(qtbot):
    panel = ConfigPanel()
    qtbot.addWidget(panel)
    panel.set_paths(Path("/a/import.json"), Path("/a/sgbd.json"))
    assert panel.config_edit.text() == str(Path("/a/import.json"))
    assert panel.sgbd_config_path() == Path("/a/sgbd.json")


def test_blank_text_reads_back_as_none(qtbot):
    panel = ConfigPanel()
    qtbot.addWidget(panel)
    panel.config_edit.setText("   ")
    assert panel.config_path() is None


def test_errors_are_shown_and_cleared(qtbot):
    panel = ConfigPanel()
    qtbot.addWidget(panel)
    panel.set_errors({"config_path": "Arquivo não encontrado: x"})
    assert "Arquivo não encontrado: x" in panel.error_label.text()
    panel.set_errors({})
    assert panel.error_label.text() == ""


def test_unrelated_errors_are_ignored(qtbot):
    panel = ConfigPanel()
    qtbot.addWidget(panel)
    panel.set_errors({"sources": "Nome de fonte repetido: stock"})
    assert panel.error_label.text() == ""
