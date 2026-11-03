"""Guard for the project's naming rule: the systems the tool writes to are
DBMSs ("SGBD" in Portuguese text), never the term the advisor rejected."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Spelled in two parts so that this guard does not match itself.
TERM = "back" + "end"

#: PEP 517 fixes this key name in pyproject.toml; it cannot be renamed.
ALLOWED = {("pyproject.toml", "build-" + TERM + ' = "setuptools.build_meta"')}


def _tracked_files():
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git ls-files is not available")
    return [p for p in out.decode("utf-8").split("\0") if p]


def _text(path: Path):
    if path.suffix.lower() == ".pdf" or not path.is_file():
        return None
    with path.open("rb") as fh:
        head = fh.read(8192)
        if b"\0" in head:
            return None
        return (head + fh.read()).decode("utf-8", errors="ignore")


def test_tracked_text_files_never_use_the_rejected_term():
    offenders = []
    for rel in _tracked_files():
        text = _text(ROOT / rel)
        if text is None:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if TERM in line.lower() and (rel, line.strip()) not in ALLOWED:
                offenders.append(f"{rel}:{n}: {line.strip()[:100]}")
    assert not offenders, f"{len(offenders)} line(s):\n" + "\n".join(offenders[:40])
