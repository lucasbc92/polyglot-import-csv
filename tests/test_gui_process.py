"""Running the CLI as a child process and streaming its output."""

import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from polyglotimportcsv.gui.process import ImportProcess  # noqa: E402

FAKE_CLI = Path(__file__).parent / "gui_fake_cli.py"


def _argv(*extra):
    return [sys.executable, str(FAKE_CLI)] + list(extra)


def test_successful_run_emits_output_then_zero(qtbot, tmp_path):
    process = ImportProcess(tmp_path)
    chunks = []
    process.output.connect(chunks.append)
    with qtbot.waitSignal(process.finished, timeout=15000) as blocker:
        process.start(_argv("0"))
    assert blocker.args == [0]
    text = "".join(chunks)
    assert "primeira linha" in text
    assert "\x1b[32m" in text
    assert "\r" in text


def test_non_zero_exit_code_is_reported(qtbot, tmp_path):
    process = ImportProcess(tmp_path)
    with qtbot.waitSignal(process.finished, timeout=15000) as blocker:
        process.start(_argv("3"))
    assert blocker.args == [3]


def test_started_signal_fires(qtbot, tmp_path):
    process = ImportProcess(tmp_path)
    with qtbot.waitSignal(process.started, timeout=15000):
        process.start(_argv("0"))
    qtbot.waitUntil(lambda: not process.is_running(), timeout=15000)


def test_stop_kills_a_long_run(qtbot, tmp_path):
    process = ImportProcess(tmp_path)
    with qtbot.waitSignal(process.started, timeout=15000):
        process.start(_argv("0", "--sleep"))
    with qtbot.waitSignal(process.finished, timeout=15000):
        process.stop()
    assert not process.is_running()


def test_missing_executable_emits_failed(qtbot, tmp_path):
    process = ImportProcess(tmp_path)
    with qtbot.waitSignal(process.failed, timeout=15000):
        process.start(["executavel-que-nao-existe-12345"])


def test_starting_twice_raises(qtbot, tmp_path):
    process = ImportProcess(tmp_path)
    with qtbot.waitSignal(process.started, timeout=15000):
        process.start(_argv("0", "--sleep"))
    with pytest.raises(RuntimeError):
        process.start(_argv("0"))
    process.stop()
    qtbot.waitUntil(lambda: not process.is_running(), timeout=15000)
