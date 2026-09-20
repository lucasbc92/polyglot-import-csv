"""The GUI entry point and its CLI hand-off."""

import subprocess
import sys
from pathlib import Path


def test_cli_flag_hands_over_without_importing_qt(monkeypatch):
    calls = {}

    def fake_cli_main(args, **kwargs):
        calls["args"] = list(args)
        return 7

    monkeypatch.setattr("polyglotimportcsv.cli.main", fake_cli_main)
    from polyglotimportcsv.gui.app import main

    assert main(["--cli", "--dry-run", "--config", "x.json"]) == 7
    assert calls["args"] == ["--dry-run", "--config", "x.json"]


def test_pyproject_declares_the_gui_script():
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'polyglotimportcsv-gui = "polyglotimportcsv.gui.app:main"' in text
    assert 'gui = ["PySide6"]' in text


def test_cli_flag_never_imports_pyside6():
    """The --cli hand-off must return before any Qt import happens.

    This is run in a fresh subprocess so the assertion is never vacuous: a
    subprocess starts with an empty ``sys.modules`` regardless of what other
    tests in this same pytest session may have already imported (pytest-qt
    based tests elsewhere import PySide6 eagerly). If PySide6 were imported
    somewhere on the ``--cli`` path, this subprocess would show it.
    """
    script = (
        "import sys\n"
        "from polyglotimportcsv.gui.app import main\n"
        "code = main(['--cli', '--help'])\n"
        "assert 'PySide6' not in sys.modules, "
        "'PySide6 was imported by the --cli hand-off'\n"
        "sys.exit(code)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
    )
    assert result.returncode == 0, (
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
