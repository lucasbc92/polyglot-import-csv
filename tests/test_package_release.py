"""Assembling the release zips from a PyInstaller dist/ and the repository."""

import importlib.util
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "package_release", ROOT / "scripts" / "package_release.py"
)
package_release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package_release)


@pytest.fixture()
def repo(tmp_path):
    """A minimal repository with every file a release ships, plus one it must not."""
    root = tmp_path / "repo"
    (root / "data" / "ecommerce").mkdir(parents=True)
    (root / "data" / "ecommerce" / "import_config.json").write_text("{}", encoding="utf-8")
    (root / "data" / "ecommerce" / "ecommerce_stock.csv").write_text("a\n1\n", encoding="utf-8")
    (root / "data" / "ecommerce" / "ecommerce_data.xlsx").write_bytes(b"not shipped")
    (root / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (root / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (root / "packaging").mkdir()
    (root / "packaging" / "LEIAME.txt").write_text("leia-me\n", encoding="utf-8")
    return root


def _names(path):
    with zipfile.ZipFile(path) as archive:
        return sorted(archive.namelist())


def test_a_zip_holds_the_executable_and_the_example(repo, tmp_path):
    exe = tmp_path / "dist" / "polyglotimportcsv.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"MZ")
    out = package_release.build_zip(repo, exe, tmp_path / "release", "polyglotimportcsv-v1.0.0-windows-x64")
    assert out.name == "polyglotimportcsv-v1.0.0-windows-x64.zip"
    prefix = "polyglotimportcsv-v1.0.0-windows-x64/"
    assert _names(out) == sorted([
        prefix + "polyglotimportcsv.exe",
        prefix + "LEIAME.txt",
        prefix + "LICENSE",
        prefix + "docker-compose.yml",
        prefix + "data/ecommerce/ecommerce_stock.csv",
        prefix + "data/ecommerce/import_config.json",
    ])


def test_the_spreadsheet_is_left_out(repo, tmp_path):
    exe = tmp_path / "polyglotimportcsv"
    exe.write_bytes(b"\x7fELF")
    out = package_release.build_zip(repo, exe, tmp_path / "release", "pkg")
    assert not any(name.endswith(".xlsx") for name in _names(out))


def test_names_are_relative_and_use_forward_slashes(repo, tmp_path):
    exe = tmp_path / "polyglotimportcsv"
    exe.write_bytes(b"\x7fELF")
    out = package_release.build_zip(repo, exe, tmp_path / "release", "pkg")
    for name in _names(out):
        assert not name.startswith("/") and ":" not in name and "\\" not in name


def test_a_unix_executable_keeps_its_execute_bit(repo, tmp_path):
    exe = tmp_path / "polyglotimportcsv"
    exe.write_bytes(b"\x7fELF")
    out = package_release.build_zip(repo, exe, tmp_path / "release", "pkg")
    with zipfile.ZipFile(out) as archive:
        mode = archive.getinfo("pkg/polyglotimportcsv").external_attr >> 16
    assert mode & 0o111


def test_package_all_builds_both_zips_for_a_platform(repo, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "polyglotimportcsv.exe").write_bytes(b"MZ")
    (dist / "polyglotimportcsv-gui.exe").write_bytes(b"MZ")
    made = package_release.package_all(repo, dist, tmp_path / "release", "v1.0.0", "windows-x64")
    assert sorted(path.name for path in made) == [
        "polyglotimportcsv-gui-v1.0.0-windows-x64.zip",
        "polyglotimportcsv-v1.0.0-windows-x64.zip",
    ]


def test_a_missing_executable_is_an_error(repo, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    with pytest.raises(FileNotFoundError):
        package_release.package_all(repo, dist, tmp_path / "release", "v1.0.0", "linux-x64")
