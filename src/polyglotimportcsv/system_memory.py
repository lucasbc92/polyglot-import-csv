"""Free physical memory of the machine, read with the standard library only.

Windows asks the kernel (``GlobalMemoryStatusEx``); Linux reads ``MemAvailable`` from
``/proc/meminfo``, the estimate of memory available to start new work without
swapping. Any other platform, or any failure, gives ``None``: callers treat the value
as advisory.
"""

from __future__ import annotations

import sys
from typing import Optional

_PROC_MEMINFO = "/proc/meminfo"
_BYTES_PER_MB = 1024 * 1024


def _windows_available_mb() -> Optional[float]:
    import ctypes
    from ctypes import wintypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", wintypes.DWORD),
            ("dwMemoryLoad", wintypes.DWORD),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return status.ullAvailPhys / _BYTES_PER_MB


def _linux_available_mb() -> Optional[float]:
    try:
        with open(_PROC_MEMINFO, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1024  # the value is in kB
    except (OSError, ValueError, IndexError):
        return None
    return None


def available_mb() -> Optional[float]:
    """Free physical memory in MiB, or ``None`` when it cannot be read."""
    try:
        if sys.platform == "win32":
            return _windows_available_mb()
        if sys.platform.startswith("linux"):
            return _linux_available_mb()
    except Exception:  # advisory value: never break a run over it
        return None
    return None
