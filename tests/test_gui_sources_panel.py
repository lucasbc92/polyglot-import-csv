"""The repeatable --source NAME=PATH table."""

from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from polyglotimportcsv.gui.widgets.sources_panel import SourcesPanel  # noqa: E402
from polyglotimportcsv.gui.widgets import sources_panel as module  # noqa: E402


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


# -- Q3: the buttons pick files, they do not make blank rows ---------------


def test_the_add_button_opens_the_file_dialog_and_adds_what_it_returns(qtbot, tmp_path):
    """The old button inserted an empty row and hid the dialog behind it."""
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    panel.set_source_kind("multi", {})
    first = tmp_path / "stock.csv"
    second = tmp_path / "purchase.csv"
    asked = []

    def choose():
        asked.append(True)
        return [str(first), str(second)]

    panel.choose_files = choose
    panel.add_button.click()
    assert asked, "clicking the button must open the file dialog"
    assert panel.sources() == (("stock", first), ("purchase", second))


def test_cancelling_the_file_dialog_adds_nothing(qtbot):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    panel.set_source_kind("multi", {})
    panel.choose_files = lambda: []
    panel.add_button.click()
    assert panel.table.rowCount() == 0


def test_the_folder_button_attaches_every_csv_in_the_folder(qtbot, tmp_path):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    panel.set_source_kind("multi", {})
    (tmp_path / "b.csv").write_text("x", encoding="utf-8")
    (tmp_path / "a.csv").write_text("x", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "deep.csv").write_text("x", encoding="utf-8")

    panel.choose_folder = lambda: str(tmp_path)
    panel.add_folder_button.click()

    names = [name for name, _ in panel.sources()]
    assert names == ["a", "b"], "only the .csv files, in a predictable order"


def test_the_folder_button_ignores_a_cancelled_dialog(qtbot):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    panel.set_source_kind("multi", {})
    panel.choose_folder = lambda: ""
    panel.add_folder_button.click()
    assert panel.table.rowCount() == 0


def test_attaching_the_same_file_twice_adds_it_once(qtbot, tmp_path):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    csv = tmp_path / "stock.csv"
    assert panel.attach([csv]) == 1
    assert panel.attach([csv]) == 0
    assert len(panel.sources()) == 1


def test_a_batch_emits_changed_once(qtbot, tmp_path):
    """A folder of twenty files must not rebuild the command twenty times."""
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    emitted = []
    panel.changed.connect(lambda: emitted.append(True))
    panel.attach([tmp_path / "a.csv", tmp_path / "b.csv", tmp_path / "c.csv"])
    assert len(emitted) == 1


def test_attach_restores_signals_after_exception(qtbot, tmp_path, monkeypatch):
    panel = SourcesPanel()
    qtbot.addWidget(panel)

    def boom(_index):
        raise RuntimeError("boom")

    monkeypatch.setattr(panel.table, "insertRow", boom)
    with pytest.raises(RuntimeError):
        panel.attach([tmp_path / "stock.csv"])
    assert panel.table.signalsBlocked() is False


# -- Q3: naming a chosen file the way the configuration does ---------------


def test_without_a_configuration_the_stem_is_used(qtbot, tmp_path):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    panel.attach([tmp_path / "ecommerce_stock.csv"])
    assert panel.sources()[0][0] == "ecommerce_stock"


def test_the_declared_file_name_names_the_row(qtbot, tmp_path):
    """The reference dataset declares "stock" and stores ecommerce_stock.csv.

    Naming that row from the stem would emit --source ecommerce_stock=..., an
    override of a source that does not exist.
    """
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    panel.set_source_kind("multi", {"stock": "ecommerce_stock.csv", "purchase": "p.csv"})
    panel.attach([tmp_path / "ecommerce_stock.csv"])
    assert panel.sources()[0][0] == "stock"


def test_a_declared_name_matches_its_own_stem(qtbot, tmp_path):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    panel.set_source_kind("multi", {"stock": "whatever.csv"})
    panel.attach([tmp_path / "stock.csv"])
    assert panel.sources()[0][0] == "stock"


def test_a_suffix_match_prefers_the_longest_declared_name(qtbot, tmp_path):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    panel.set_source_kind("multi", {"stock": "a.csv", "restock": "b.csv"})
    panel.attach([tmp_path / "loja_restock.csv"])
    assert panel.sources()[0][0] == "restock"


def test_an_unrecognised_file_keeps_its_stem(qtbot, tmp_path):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    panel.set_source_kind("multi", {"stock": "ecommerce_stock.csv"})
    panel.attach([tmp_path / "outra_coisa.csv"])
    assert panel.sources()[0][0] == "outra_coisa"


def test_errors_are_shown(qtbot):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    panel.set_errors({"sources": "Nome de fonte repetido: stock"})
    assert panel.error_label.text() == "Nome de fonte repetido: stock"
    panel.set_errors({})
    assert panel.error_label.text() == ""


def test_add_row_restores_signals_after_exception(qtbot, monkeypatch):
    panel = SourcesPanel()
    qtbot.addWidget(panel)

    def boom(_index):
        raise RuntimeError("boom")

    monkeypatch.setattr(panel.table, "insertRow", boom)
    with pytest.raises(RuntimeError):
        panel.add_row("stock", "/d/stock.csv")
    assert panel.table.signalsBlocked() is False


def test_remove_selected_rows_restores_signals_after_exception(qtbot, monkeypatch):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    panel.add_row("a", "/d/a.csv")
    panel.table.selectRow(0)

    def boom(_index):
        raise RuntimeError("boom")

    monkeypatch.setattr(panel.table, "removeRow", boom)
    with pytest.raises(RuntimeError):
        panel.remove_selected_rows()
    assert panel.table.signalsBlocked() is False


# -- Q7: the card adapts to the kind of import configuration ---------------

from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDropEvent  # noqa: E402
from PySide6.QtWidgets import QAbstractItemView  # noqa: E402


def _combined(panel):
    panel.set_source_kind("combined", {"ecommerce": "ecommerce_join.csv"})


def test_without_a_configuration_nothing_can_be_added(qtbot):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    assert not panel.add_button.isEnabled()
    assert not panel.add_folder_button.isEnabled()
    assert not panel.table.acceptDrops()
    assert panel.kind_label.text() == module.NO_CONFIG_TEXT


def test_a_multi_config_allows_many_files_and_folders(qtbot):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    panel.set_source_kind("multi", {"stock": "s.csv", "purchase": "p.csv"})
    assert panel.add_button.isEnabled()
    assert panel.add_button.text() == "+ Adicionar arquivos"
    assert panel.add_folder_button.isEnabled()
    assert panel.kind_label.text() == module.MULTI_TEXT
    assert panel.table.selectionMode() == QAbstractItemView.ExtendedSelection


def test_a_combined_config_takes_one_file_named_after_the_source(qtbot, tmp_path):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    _combined(panel)
    assert panel.add_button.text() == "+ Adicionar arquivo"
    assert not panel.add_folder_button.isEnabled()
    assert panel.add_folder_button.toolTip()
    assert panel.kind_label.text() == module.COMBINED_TEXT
    assert panel.table.selectionMode() == QAbstractItemView.SingleSelection
    panel.choose_files = lambda: [str(tmp_path / "qualquer_nome.csv")]
    panel.add_button.click()
    assert panel.sources() == (("ecommerce", tmp_path / "qualquer_nome.csv"),)
    assert not panel.add_button.isEnabled(), "one file is all a combined config takes"


def test_removing_the_combined_file_enables_adding_again(qtbot, tmp_path):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    _combined(panel)
    panel.attach([tmp_path / "a.csv"])
    panel.table.selectRow(0)
    panel.remove_selected_rows()
    assert panel.add_button.isEnabled()


def test_a_combined_config_refuses_a_second_file(qtbot, tmp_path):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    _combined(panel)
    assert panel.drop_paths([tmp_path / "a.csv", tmp_path / "b.csv"]) == 0
    assert panel.table.rowCount() == 0
    assert panel.error_label.text() == module.ONE_FILE_ERROR


def test_dropping_files_attaches_the_csv_ones(qtbot, tmp_path):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    panel.set_source_kind("multi", {})
    added = panel.drop_paths([tmp_path / "a.csv", tmp_path / "notas.txt"])
    assert added == 1
    assert [name for name, _ in panel.sources()] == ["a"]
    assert "1 arquivo ignorado" in panel.error_label.text()


def test_dropping_a_folder_on_a_multi_config_attaches_its_csvs(qtbot, tmp_path):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    panel.set_source_kind("multi", {})
    (tmp_path / "b.csv").write_text("x", encoding="utf-8")
    (tmp_path / "a.csv").write_text("x", encoding="utf-8")
    assert panel.drop_paths([tmp_path]) == 2


def test_dropping_without_a_configuration_adds_nothing(qtbot, tmp_path):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    assert panel.drop_paths([tmp_path / "a.csv"]) == 0
    assert panel.table.rowCount() == 0


def test_a_real_drop_event_reaches_the_panel(qtbot, tmp_path):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    panel.set_source_kind("multi", {})
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(tmp_path / "estoque.csv"))])
    event = QDropEvent(QPointF(5, 5), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    panel.table.dropEvent(event)
    assert [name for name, _ in panel.sources()] == ["estoque"]


def test_remove_is_enabled_only_with_a_selection(qtbot, tmp_path):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    panel.set_source_kind("multi", {})
    panel.attach([tmp_path / "a.csv"])
    assert not panel.remove_button.isEnabled()
    panel.table.selectRow(0)
    assert panel.remove_button.isEnabled()


def test_rows_survive_losing_the_configuration(qtbot, tmp_path):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    panel.set_source_kind("multi", {})
    panel.attach([tmp_path / "a.csv"])
    panel.set_source_kind(None, None)
    assert panel.table.rowCount() == 1
    assert not panel.add_button.isEnabled()
    panel.table.selectRow(0)
    assert panel.remove_button.isEnabled(), "what was chosen can still be removed"


def test_the_empty_table_paints_its_placeholder(qtbot):
    panel = SourcesPanel()
    qtbot.addWidget(panel)
    panel.set_source_kind("multi", {})
    panel.show()
    assert panel.table.grab().toImage().width() > 0  # paintEvent ran without error
    assert "Arraste" in module.CsvDropTable.PLACEHOLDER
