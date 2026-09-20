"""The repeatable --source NAME=PATH table."""

from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from polyglotimportcsv.gui.widgets.sources_panel import SourcesPanel  # noqa: E402


def test_starts_empty(qtbot):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    assert panel.sources() == ()
    assert panel.table.rowCount() == 0


def test_add_row_then_fill_it(qtbot):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    row = panel.add_row("stock", "/d/stock.csv")
    assert row == 0
    assert panel.sources() == (("stock", Path("/d/stock.csv")),)


def test_blank_rows_are_ignored(qtbot):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    panel.add_row()
    assert panel.sources() == ()


def test_a_half_filled_row_is_reported_as_is(qtbot):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    panel.add_row("stock", "")
    assert panel.sources() == (("stock", Path("")),)


def test_editing_a_cell_emits_changed(qtbot):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    panel.add_row("stock", "/d/stock.csv")
    with qtbot.waitSignal(panel.changed, timeout=1000):
        panel.table.item(0, 0).setText("purchase")
    assert panel.sources()[0][0] == "purchase"


def test_remove_selected_rows(qtbot):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    panel.add_row("a", "/d/a.csv")
    panel.add_row("b", "/d/b.csv")
    panel.table.selectRow(0)
    panel.remove_selected_rows()
    assert panel.sources() == (("b", Path("/d/b.csv")),)


def test_add_button_appends_a_row(qtbot):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    panel.add_button.click()
    assert panel.table.rowCount() == 1


def test_errors_are_shown(qtbot):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    panel.set_errors({"sources": "Nome de fonte repetido: stock"})
    assert panel.error_label.text() == "Nome de fonte repetido: stock"
    panel.set_errors({})
    assert panel.error_label.text() == ""
