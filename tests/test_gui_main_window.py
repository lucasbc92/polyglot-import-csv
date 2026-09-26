"""Wiring: form -> command -> process -> console."""

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from polyglotimportcsv.gui import launcher  # noqa: E402
from polyglotimportcsv.gui.widgets.main_window import MainWindow  # noqa: E402


from PySide6.QtCore import QEvent, QSettings, Qt  # noqa: E402


@pytest.fixture()
def config_files(tmp_path):
    """A minimal configuration the CLI's own dry-run accepts (checked 26/09)."""
    (tmp_path / "items.csv").write_text("id,name\n1,a\n", encoding="utf-8")
    cfg = tmp_path / "import_config.json"
    cfg.write_text(
        json.dumps({
            "sources": {"items": "items.csv"},
            "postgres": {"entities": {"items": {"columns": {"id": {"is_key": True}, "name": {}}}}},
            "redis": {"entities": {"items": {"columns": {"id": {"is_key": True}, "name": {}}}}},
        }),
        encoding="utf-8",
    )
    sgbd = tmp_path / "sgbd_config.json"
    sgbd.write_text(
        json.dumps({
            "version": 1,
            "postgres": {"connection": {"host": "localhost", "port": 5432, "database": "d",
                                        "user": "u", "password": "p"}},
            "redis": {"connection": {"host": "localhost", "port": 6379, "db": 0}},
        }),
        encoding="utf-8",
    )
    return cfg, sgbd


@pytest.fixture()
def window(qtbot, tmp_path):
    """A window with throwaway settings, so no test reads the real ones."""
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    widget = MainWindow(settings=settings)
    qtbot.addWidget(widget)
    return widget


def test_window_opens_showing_the_defaults_it_would_run_with(window):
    """Q1: no configuration chosen yet, but the options still have values.

    Before, the command was the bare program name until something was changed,
    which hid the fact that a run already had a strategy, an execution mode and
    a log level picked out for it.
    """
    assert window.console_panel.command_text() == (
        "polyglotimportcsv --strategy optimized --execution stream "
        "--create-schema --log-level INFO --sample 50"
    )


def test_choosing_a_config_updates_the_command(window, config_files):
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    assert "--config" in window.console_panel.command_text()
    assert str(cfg) in window.console_panel.command_text()


def test_toggling_an_option_updates_the_command(window, config_files):
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    window.options_panel.dry_run_box.setChecked(True)
    assert "--dry-run" in window.console_panel.command_text()


def test_run_is_disabled_until_the_form_is_valid(window, config_files):
    cfg, _ = config_files
    assert not window.console_panel.run_button.isEnabled()
    window.config_panel.set_paths(cfg, None)
    assert window.console_panel.run_button.isEnabled()


def test_validation_errors_reach_the_panels(window, tmp_path):
    window.config_panel.set_paths(tmp_path / "ausente.json", None)
    assert "Arquivo não encontrado" in window.config_panel.error_label.text()


def test_edit_mode_disables_the_form(window, config_files):
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    window.console_panel.set_editing(True)
    assert not window.config_panel.isEnabled()
    assert not window.options_panel.isEnabled()
    assert not window.sources_panel.isEnabled()
    window.console_panel.set_editing(False)
    assert window.config_panel.isEnabled()


def test_reactivating_the_window_reruns_preflight_after_an_external_fix(window, config_files):
    """A config fixed in an external editor never changes the QLineEdit text,
    so no ``changed`` signal fires. Reactivating the window must pick up the
    fix anyway, instead of leaving Run disabled with the stale error."""
    cfg, sgbd = config_files
    good = cfg.read_text(encoding="utf-8")
    broken = good.replace('"id":', '"id_errado":')
    cfg.write_text(broken, encoding="utf-8")

    window.config_panel.set_paths(cfg, sgbd)
    assert not window.console_panel.run_button.isEnabled()
    assert window.config_panel.error_label.text() != ""

    cfg.write_text(good, encoding="utf-8")
    stat = cfg.stat()
    os.utime(cfg, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10_000_000))

    window.isActiveWindow = lambda: True
    window.changeEvent(QEvent(QEvent.ActivationChange))

    assert window.console_panel.run_button.isEnabled()
    assert window.config_panel.error_label.text() == ""


def test_reactivating_the_window_does_not_refresh_while_a_run_is_in_progress(
    window, config_files, monkeypatch
):
    """The Run button doubles as Interromper while a process runs; a
    reactivation-triggered refresh must not touch the form then."""
    cfg, sgbd = config_files
    window.config_panel.set_paths(cfg, sgbd)
    monkeypatch.setattr(window.process, "is_running", lambda: True)

    calls = []
    window.refresh_command = lambda: calls.append(1)
    window.isActiveWindow = lambda: True
    window.changeEvent(QEvent(QEvent.ActivationChange))

    assert not calls, "refresh_command must not run while a process is in progress"


def test_reactivating_the_window_does_not_refresh_while_editing_the_console(
    window, config_files
):
    cfg, sgbd = config_files
    window.config_panel.set_paths(cfg, sgbd)
    window.console_panel.set_editing(True)

    calls = []
    window.refresh_command = lambda: calls.append(1)
    window.isActiveWindow = lambda: True
    window.changeEvent(QEvent(QEvent.ActivationChange))

    assert not calls


def test_reactivating_an_inactive_window_does_not_refresh(window, config_files):
    cfg, sgbd = config_files
    window.config_panel.set_paths(cfg, sgbd)

    calls = []
    window.refresh_command = lambda: calls.append(1)
    window.isActiveWindow = lambda: False
    window.changeEvent(QEvent(QEvent.ActivationChange))

    assert not calls


def test_argv_for_run_uses_the_launcher_prefix(window, config_files):
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    argv = window.argv_for_run()
    assert argv[1:3] == ["-m", "polyglotimportcsv"]
    assert argv[3] == "--config"


def test_argv_for_run_in_edit_mode_uses_the_typed_text(window, config_files):
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    window.console_panel.set_editing(True)
    window.console_panel.command_edit.setPlainText("polyglotimportcsv --dry-run")
    argv = window.argv_for_run()
    assert argv[-1] == "--dry-run"
    assert argv == launcher.resolve() + ["--dry-run"]


def test_edit_mode_keeps_every_token_when_the_program_name_is_absent(window, config_files):
    """I5: dropping tokens[0] unconditionally ran the CLI with no arguments."""
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    window.console_panel.set_editing(True)
    window.console_panel.command_edit.setPlainText("--dry-run --no-data")
    assert window.argv_for_run() == launcher.resolve() + ["--dry-run", "--no-data"]


def test_edit_mode_drops_a_program_name_written_as_a_full_path(window, config_files):
    """I5: an .exe suffix or a path prefix still names the program."""
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    window.console_panel.set_editing(True)
    window.console_panel.command_edit.setPlainText(
        r'"C:\venv\Scripts\polyglotimportcsv.exe" --dry-run'
    )
    assert window.argv_for_run() == launcher.resolve() + ["--dry-run"]


def test_edit_mode_enables_run_even_with_an_invalid_form(window):
    """I6: the opening move — no config chosen, type a whole command by hand."""
    assert not window.console_panel.run_button.isEnabled()
    window.console_panel.set_editing(True)
    window.console_panel.command_edit.setPlainText(
        "polyglotimportcsv --config c.json --dry-run"
    )
    assert window.console_panel.run_button.isEnabled()


def test_launcher_prefix_tooltip_is_installed_on_the_console_panel(window):
    """I3 / §6.1: the resolved prefix is visible in the interface itself."""
    assert " ".join(launcher.resolve()) in window.console_panel.command_edit.toolTip()


def test_declared_dbms_filter_the_checkboxes(window, config_files):
    cfg, sgbd = config_files
    window.config_panel.set_paths(cfg, sgbd)
    assert window.options_panel.dbms_boxes["postgres"].isEnabled()
    assert not window.options_panel.dbms_boxes["neo4j"].isEnabled()


def test_unreadable_sgbd_config_leaves_every_checkbox_enabled(window, tmp_path, config_files):
    cfg, _ = config_files
    broken = tmp_path / "quebrado.json"
    broken.write_text("{ nao e json", encoding="utf-8")
    window.config_panel.set_paths(cfg, broken)
    assert all(box.isEnabled() for box in window.options_panel.dbms_boxes.values())


def test_finishing_with_zero_sets_a_success_status(window, config_files):
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    window._on_finished(0)
    assert "Concluído" in window.status_label.text()


def test_finishing_with_non_zero_sets_an_error_status(window, config_files):
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    window._on_finished(2)
    assert "código de saída 2" in window.status_label.text()


# The real shape printed by reporting.kv("Log file", log_path): a leading
# indent, a colon after the label, one space, then path.resolve() — an
# absolute path, which on Windows routinely contains spaces.
REAL_LOG_PATH = r"C:\Users\Lucas Bueno\proj\logs\session-20260920-142233.log"
REAL_LOG_LINE = "    Log file: " + REAL_LOG_PATH


def test_log_path_is_picked_up_from_the_output(window):
    window._on_output(REAL_LOG_LINE + "\n")
    assert window.log_path_label.text() == REAL_LOG_PATH


def test_log_path_keeps_the_spaces_of_an_absolute_windows_path(window):
    r"""I4: the old \S+ stopped at the first space and showed "C:\Users\Lucas"."""
    window._on_output(REAL_LOG_LINE + "\r\n")
    assert window.log_path_label.text() == REAL_LOG_PATH
    assert " " in window.log_path_label.text()


def test_log_path_survives_a_split_across_two_chunks(window):
    """I1 robustness: readyRead can split the line at any byte boundary."""
    window._on_output("    Log file: " + REAL_LOG_PATH[:-12])
    window._on_output(REAL_LOG_PATH[-12:] + "\r\n")
    assert window.log_path_label.text() == REAL_LOG_PATH


def test_log_path_ignores_a_surrounding_colour_escape(window):
    """I1 robustness: FORCE_COLOR=1 can wrap the dim label in SGR codes."""
    window._on_output("\x1b[2m    Log file: \x1b[0m" + REAL_LOG_PATH + "\n")
    assert window.log_path_label.text() == REAL_LOG_PATH


def test_finishing_flushes_a_pending_partial_escape(window, config_files):
    """Ruling 1: a lone trailing partial escape must not be stranded forever."""
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    window.console_panel.append_output("linha\x1b[3")
    assert "[3" not in window.console_panel.log_view.toPlainText()
    window._on_finished(0)
    assert "[3" in window.console_panel.log_view.toPlainText()


def test_finishing_does_not_reenable_the_form_while_editing(window, config_files):
    """I2: edit mode must stay in force across a run that ends while active."""
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    window.console_panel.set_editing(True)
    window._on_finished(0)
    assert not window.config_panel.isEnabled()
    assert not window.options_panel.isEnabled()
    assert not window.sources_panel.isEnabled()


def test_failing_does_not_reenable_the_form_while_editing(window, config_files):
    """I2: same invariant on the failure path."""
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    window.console_panel.set_editing(True)
    window._on_failed("não foi possível iniciar o processo")
    assert not window.config_panel.isEnabled()


def test_on_run_rejects_unbalanced_quotes_in_edit_mode(window, config_files):
    """I3: a malformed edited command must not raise or start a process."""
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    window.console_panel.set_editing(True)
    window.console_panel.command_edit.setPlainText('polyglotimportcsv --config "C:\\a b.json')
    window.on_run()
    assert "inválido" in window.status_label.text().lower()
    assert not window.process.is_running()


def test_on_run_preserves_previous_log_on_a_rejected_command(window, config_files):
    """I3: a rejected command must not wipe out the previous run's output."""
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    window.console_panel.append_output("saída da execução anterior\n")
    window.console_panel.set_editing(True)
    window.console_panel.command_edit.setPlainText('polyglotimportcsv --config "C:\\a b.json')
    window.on_run()
    assert "saída da execução anterior" in window.console_panel.log_view.toPlainText()


# -- fix round 2 (C3): the happy path through on_run(), end to end ----------


def test_a_full_run_shows_the_child_output_in_the_console(qtbot, window, config_files, monkeypatch):
    """C3: on_run -> process.start -> _on_output -> _on_finished, for real.

    The whole chain had never been exercised: every earlier test called
    on_run() only on its rejection path or poked _on_finished() directly, so
    a run whose console stayed completely blank still reported "Concluído"
    and passed. This test asserts the child's own text is visible, which is
    what C1 (CRLF wiping every line) made false.
    """
    import sys

    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    fake_cli = Path(__file__).parent / "gui_fake_cli.py"
    monkeypatch.setattr(
        window, "argv_for_run", lambda: [sys.executable, str(fake_cli), "0"]
    )

    with qtbot.waitSignal(window.process.finished, timeout=15000) as blocker:
        window.on_run()
    assert blocker.args == [0]
    qtbot.waitUntil(lambda: "Concluído" in window.status_label.text(), timeout=5000)

    text = window.console_panel.log_view.toPlainText()
    assert "primeira linha" in text
    assert "segunda linha" in text
    # The bare "\r" redraw still collapses onto one line, as rich intends.
    assert "progresso 90%" in text
    assert "progresso 10%" not in text
    # And no line the child wrote was erased by its own CRLF terminator.
    body = [line for line in text.splitlines() if line.strip()]
    assert len(body) >= 4  # "Executando: …" plus the three child lines


def test_a_full_run_re_enables_the_form_and_clears_the_running_badge(
    qtbot, window, config_files, monkeypatch
):
    """C3: the run must land back in the idle state, not stay stuck."""
    import sys

    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    fake_cli = Path(__file__).parent / "gui_fake_cli.py"
    monkeypatch.setattr(
        window, "argv_for_run", lambda: [sys.executable, str(fake_cli), "3"]
    )

    with qtbot.waitSignal(window.process.finished, timeout=15000):
        window.on_run()
    qtbot.waitUntil(lambda: "código de saída 3" in window.status_label.text(), timeout=5000)
    assert window.config_panel.isEnabled()
    assert "Executar" in window.console_panel.run_button.text()


# -- Task 9: preflight, source kind, save log, clickable path --------------


def test_a_preflight_error_blocks_the_run_and_reaches_the_config_card(window, config_files):
    cfg, _ = config_files
    cfg.write_text('{"postgres": {}}', encoding="utf-8")  # no "sources": schema error
    window.config_panel.set_paths(cfg, None)
    assert "sources" in window.config_panel.error_label.text()
    assert not window.console_panel.run_button.isEnabled()


def test_choosing_a_config_tells_the_sources_card_its_kind(window, config_files):
    cfg, _ = config_files
    assert not window.sources_panel.add_button.isEnabled()
    window.config_panel.set_paths(cfg, None)
    assert window.sources_panel.add_button.isEnabled()
    assert "multifonte" in window.sources_panel.kind_label.text()


def test_switching_to_a_combined_config_keeps_rows_and_blocks_the_run(
    window, config_files, tmp_path
):
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    other = tmp_path / "items_b.csv"
    other.write_text("id,name\n2,b\n", encoding="utf-8")
    # Two distinct names, so the local "repeated name" rule stays out of the way.
    window.sources_panel.add_row("items", str(tmp_path / "items.csv"))
    window.sources_panel.add_row("outra", str(other))
    combined = tmp_path / "combinada.json"
    combined.write_text(
        json.dumps({
            "sources": {"tudo": {"file": "items.csv", "origin_column": True}},
            "postgres": {"entities": {"items": {"columns": {"name": {"is_key": True}}}}},
        }),
        encoding="utf-8",
    )
    window.config_panel.set_paths(combined, None)
    assert window.sources_panel.table.rowCount() == 2, "nothing is thrown away"
    assert not window.sources_panel.add_button.isEnabled()
    assert window.sources_panel.error_label.text() == (
        "A configuração combinada aceita um único arquivo CSV."
    )
    assert not window.console_panel.run_button.isEnabled()


def test_the_sample_size_reaches_the_command(window, config_files):
    cfg, _ = config_files
    window.config_panel.set_paths(cfg, None)
    window.options_panel.sample_spin.setValue(7)
    assert "--sample 7" in window.console_panel.command_text()


def test_save_log_offers_the_log_after_a_run(window, tmp_path):
    log = tmp_path / "logs" / "polyglotimportcsv_20260926_101010.log"
    log.parent.mkdir()
    log.write_text("conteudo do log", encoding="utf-8")
    window._on_output("    Log file: {0}\n".format(log))
    window._on_finished(0)
    assert window.console_panel.save_log_button.isEnabled()

    target = tmp_path / "copia.log"
    suggested = []

    def choose(path):
        suggested.append(path)
        return str(target)

    window.choose_log_destination = choose
    window.console_panel.save_log_button.click()
    assert suggested and suggested[0].name == log.name
    assert target.read_text(encoding="utf-8") == "conteudo do log"
    assert str(target) in window.status_label.text()


def test_cancelling_save_log_writes_nothing(window, tmp_path):
    log = tmp_path / "sessao.log"
    log.write_text("x", encoding="utf-8")
    window._on_output("    Log file: {0}\n".format(log))
    window._on_finished(0)
    window.choose_log_destination = lambda path: ""
    window.console_panel.save_log_button.click()
    assert list(tmp_path.iterdir()) == [log]


def test_a_failed_copy_is_reported(window, tmp_path):
    log = tmp_path / "sessao.log"
    log.write_text("x", encoding="utf-8")
    window._on_output("    Log file: {0}\n".format(log))
    window._on_finished(0)
    errors = []
    window.show_error = errors.append
    window.choose_log_destination = lambda path: str(tmp_path / "nao" / "existe" / "x.log")
    window.console_panel.save_log_button.click()
    assert errors and "log" in errors[0].lower()


def test_no_log_means_nothing_to_save(window):
    window._on_finished(0)
    assert not window.console_panel.save_log_button.isEnabled()


def test_a_new_run_withdraws_the_previous_log(window, config_files, tmp_path, monkeypatch):
    cfg, _ = config_files
    log = tmp_path / "sessao.log"
    log.write_text("x", encoding="utf-8")
    window.config_panel.set_paths(cfg, None)
    window._on_output("    Log file: {0}\n".format(log))
    window._on_finished(0)
    monkeypatch.setattr(window.process, "start", lambda *a, **k: None)
    window.on_run()
    assert not window.console_panel.save_log_button.isEnabled()
    assert window.log_path() is None


def test_clicking_the_log_path_opens_its_folder(window, qtbot, tmp_path):
    log = tmp_path / "logs" / "sessao.log"
    window._on_output("    Log file: {0}\n".format(log))
    opened = []
    window.open_folder = opened.append
    qtbot.mouseClick(window.log_path_label, Qt.LeftButton)
    assert opened == [log.parent]
