"""``system_memory.available_mb``: free physical memory, read without third-party packages.

The campaign runner records it per run (to check that runs started under comparable
conditions) and the automatic block size will size the read block from it.
"""

import sys

from polyglotimportcsv import system_memory


def test_available_memory_is_a_positive_number_on_this_machine():
    free = system_memory.available_mb()
    assert isinstance(free, float) and free > 0


def test_an_unsupported_platform_gives_none(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert system_memory.available_mb() is None


def test_linux_reads_memavailable_from_proc_meminfo(monkeypatch, tmp_path):
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:  8000000 kB\nMemFree:  100000 kB\nMemAvailable:  2097152 kB\n",
                       encoding="utf-8")
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(system_memory, "_PROC_MEMINFO", str(meminfo))
    assert system_memory.available_mb() == 2048.0


def test_an_unreadable_meminfo_gives_none(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(system_memory, "_PROC_MEMINFO", str(tmp_path / "missing"))
    assert system_memory.available_mb() is None
