"""Turn the form state into the CLI argv, and into the text the panel shows.

Every option the form can set is written out in full, including the ones left
at the CLI's own default. Emitting only the differences made the command
shorter but made three controls look broken: selecting "optimized", "stream" or
"Criar esquema" — each already the default — changed nothing on screen, so the
click seemed to have been ignored. A visible, complete command is worth more
here than a short one, because the panel doubles as documentation of what will
actually run.

Two options have no spelled-out "off": ``--dry-run`` and ``--benchmark`` are
switches with no negative form in the CLI, and "Automático" for the data dump
is the absence of both ``--show-data`` and ``--no-data``. Their absence *is*
their default, so toggling them still changes the command.
"""

from __future__ import annotations

import os
import shlex
from typing import List, Optional, Sequence

from polyglotimportcsv.gui.state import RunOptions

PROGRAM = "polyglotimportcsv"


def build_argv(options: RunOptions) -> List[str]:
    """Return the CLI arguments (without the program name) for ``options``."""
    argv = []  # type: List[str]
    if options.config_path is not None:
        argv += ["--config", str(options.config_path)]
    if options.sgbd_config_path is not None:
        argv += ["--sgbd-config", str(options.sgbd_config_path)]
    if options.only:
        argv += ["--only", ",".join(options.only)]
    argv += ["--strategy", options.strategy]
    argv += ["--execution", options.execution]
    if options.dry_run:
        argv.append("--dry-run")
    argv.append("--create-schema" if options.create_schema else "--no-create-schema")
    if options.benchmark:
        argv.append("--benchmark")
    argv += ["--log-level", options.log_level]
    if options.show_data is True:
        argv.append("--show-data")
    elif options.show_data is False:
        argv.append("--no-data")
    for name, path in options.sources:
        argv += ["--source", "{0}={1}".format(name, path)]
    return argv


def is_program_token(token: str) -> bool:
    """True when ``token`` names this program rather than one of its options.

    Used by edit mode to decide whether the first token typed is the program
    name — which the resolved launcher prefix replaces — or already an
    argument. Blindly dropping the first token turned a typed ``--dry-run``
    into a run with no arguments at all. A bare name, a name with ``.exe``,
    and a full path to either all count as the program name; anything else
    (notably anything starting with ``-``) does not. This is a single-token
    identity check, not a command parser.
    """
    name = token.strip('"').replace("\\", "/").rsplit("/", 1)[-1]
    if name.lower().endswith(".exe"):
        name = name[:-4]
    return name.lower() == PROGRAM


def quote(token: str, windows: Optional[bool] = None) -> str:
    """Quote one token the way the host shell would display it."""
    if windows is None:
        windows = os.name == "nt"
    if not windows:
        return shlex.quote(token)
    if token and not any(ch in token for ch in ' \t"'):
        return token
    return '"' + token.replace('"', '\\"') + '"'


def to_display(argv: Sequence[str], windows: Optional[bool] = None) -> str:
    """Render ``argv`` as the one-line command shown in the console panel."""
    return " ".join([PROGRAM] + [quote(token, windows) for token in argv])
