"""Assemble the release zips from a PyInstaller ``dist/`` and the repository.

Each platform gets two archives, one per executable: the CLI
(``polyglotimportcsv``) and the GUI (``polyglotimportcsv-gui``, which is also a
complete CLI when started with ``--cli``). Both carry the e-commerce example,
``docker-compose.yml``, the licence and a bilingual README, so the tool can be tried
right after download. The spreadsheet in ``data/ecommerce/`` is a working file
of the author and is left out.

Usage, from the repository root, after ``pyinstaller polyglotimportcsv.spec``::

    python scripts/package_release.py --tag v1.0.0 --os windows-x64
"""

from __future__ import annotations

import argparse
import stat
import sys
import zipfile
from pathlib import Path
from typing import Iterator, List, Tuple

REPO = Path(__file__).resolve().parent.parent
EXECUTABLES = ("polyglotimportcsv", "polyglotimportcsv-gui")
PLATFORMS = ("windows-x64", "linux-x64")
EXCLUDED_SUFFIXES = (".xlsx",)


def _payload(repo: Path) -> Iterator[Tuple[Path, str]]:
    """``(source file, path inside the package)`` for everything but the executable."""
    for path in sorted((repo / "data" / "ecommerce").rglob("*")):
        if path.is_file() and path.suffix.lower() not in EXCLUDED_SUFFIXES:
            yield path, path.relative_to(repo).as_posix()
    yield repo / "docker-compose.yml", "docker-compose.yml"
    yield repo / "LICENSE", "LICENSE"
    yield repo / "packaging" / "README.md", "README.md"


def build_zip(repo: Path, executable: Path, out_dir: Path, name: str) -> Path:
    """Write ``out_dir/name.zip`` with every entry under a ``name/`` folder."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / (name + ".zip")
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        # Written by hand so the execute bit survives on Linux: ZipFile.write
        # would store the mode of the build machine's file, which is fine on
        # the Linux runner but meaningless for a file built on Windows.
        info = zipfile.ZipInfo(name + "/" + executable.name)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = (stat.S_IFREG | 0o755) << 16
        archive.writestr(info, executable.read_bytes())
        for source, inside in _payload(repo):
            archive.write(source, name + "/" + inside)
    return target


def package_all(repo: Path, dist: Path, out_dir: Path, tag: str, platform: str) -> List[Path]:
    """Build the CLI and GUI zips of one platform; fail if an executable is missing."""
    suffix = ".exe" if platform.startswith("windows") else ""
    made = []  # type: List[Path]
    for program in EXECUTABLES:
        executable = dist / (program + suffix)
        if not executable.is_file():
            raise FileNotFoundError("executable not found: {0}".format(executable))
        made.append(build_zip(repo, executable, out_dir, "{0}-{1}-{2}".format(program, tag, platform)))
    return made


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", required=True, help="release tag, e.g. v1.0.0")
    parser.add_argument("--os", dest="platform", required=True, choices=PLATFORMS)
    parser.add_argument("--dist", type=Path, default=REPO / "dist")
    parser.add_argument("--out", type=Path, default=REPO / "release")
    args = parser.parse_args(argv)
    for path in package_all(REPO, args.dist, args.out, args.tag, args.platform):
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
