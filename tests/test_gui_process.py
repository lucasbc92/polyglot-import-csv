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


@pytest.fixture
def process(tmp_path, qtbot):
    """An ImportProcess that always gets stopped, even if the test fails.

    Without this, a failing assertion or timed-out waitSignal would abort the
    test before its inline `stop()` ran, leaving a 30-second sleeping child
    behind for the tests that use `--sleep`.
    """
    instance = ImportProcess(tmp_path)
    yield instance
    instance.stop()
    qtbot.waitUntil(lambda: not instance.is_running(), timeout=15000)


def test_successful_run_emits_output_then_zero(qtbot, process):
    chunks = []
    process.output.connect(chunks.append)
    with qtbot.waitSignal(process.finished, timeout=15000) as blocker:
        process.start(_argv("0"))
    assert blocker.args == [0]
    text = "".join(chunks)
    assert "primeira linha" in text
    assert "\x1b[32m" in text
    assert "\r" in text


def test_non_zero_exit_code_is_reported(qtbot, process):
    with qtbot.waitSignal(process.finished, timeout=15000) as blocker:
        process.start(_argv("3"))
    assert blocker.args == [3]


def test_started_signal_fires(qtbot, process):
    with qtbot.waitSignal(process.started, timeout=15000):
        process.start(_argv("0"))
    qtbot.waitUntil(lambda: not process.is_running(), timeout=15000)


def test_stop_kills_a_long_run(qtbot, process):
    with qtbot.waitSignal(process.started, timeout=15000):
        process.start(_argv("0", "--sleep"))
    with qtbot.waitSignal(process.finished, timeout=15000):
        process.stop()
    assert not process.is_running()


def test_missing_executable_emits_failed(qtbot, process):
    with qtbot.waitSignal(process.failed, timeout=15000):
        process.start(["executavel-que-nao-existe-12345"])


def test_starting_twice_raises(qtbot, process):
    with qtbot.waitSignal(process.started, timeout=15000):
        process.start(_argv("0", "--sleep"))
    with pytest.raises(RuntimeError):
        process.start(_argv("0"))


def test_crash_emits_finished_not_failed(qtbot, process):
    """A genuine crash (not our own stop()) must fire finished, not failed.

    We reach into `process._process` to kill the underlying QProcess
    directly, bypassing our own stop()/terminate() path, so that Qt's
    errorOccurred(Crashed) + finished(exitCode, CrashExit) sequence is
    exercised exactly as it would be for an external kill, a segfault, or an
    OOM kill. This is acceptable here because the test is specifically about
    that internal boundary.
    """
    failures = []
    process.failed.connect(failures.append)
    with qtbot.waitSignal(process.started, timeout=15000):
        process.start(_argv("0", "--sleep"))
    with qtbot.waitSignal(process.finished, timeout=15000):
        process._process.kill()
    assert failures == []
