"""Decide which process to spawn, and with which environment.

The panel always shows ``polyglotimportcsv <args>`` because that is what a
person would type; what we spawn needs a real interpreter in front of it. This
prefix is the only difference between the two, and it is logged on every run.
"""

from __future__ import annotations

import sys
from typing import Dict, List

CLI_FLAG = "--cli"
MIN_COLUMNS = 40


def resolve() -> List[str]:
    """Return the process prefix that runs the CLI in this installation."""
    if getattr(sys, "frozen", False):
        return [sys.executable, CLI_FLAG]
    return [sys.executable, "-m", "polyglotimportcsv"]


def child_environment(columns: int, color: bool) -> Dict[str, str]:
    """Variables to add to the inherited environment of the child process."""
    env = {
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        "COLUMNS": str(max(MIN_COLUMNS, int(columns))),
    }
    if color:
        env["FORCE_COLOR"] = "1"
    return env
