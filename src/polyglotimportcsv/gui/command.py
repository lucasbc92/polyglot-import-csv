"""Turn the form state into the CLI argv, and into the text the panel shows.

Every option the form can set is written out in full, including the ones left
at the CLI's own default. Emitting only the differences made the command
shorter but made three controls look broken: selecting "optimized", "stream" or
"Criar esquema" — each already the default — changed nothing on screen, so the
click seemed to have been ignored. A visible, complete command is worth more
here than a short one, because the panel doubles as documentation of what will
actually run.

``--dry-run`` is a switch with no negative form in the CLI, so its absence is
its default. ``--strategy optimized`` is written even though the form offers
no choice: it is what runs, and the command shows what runs. The data display
is always spelled out: ``--sample N``, ``--show-data`` or ``--no-data``.
"""

from __future__ import annotations

import os
import re
import shlex
from typing import List, Optional, Sequence, Tuple

from polyglotimportcsv.gui.state import STRATEGY, RunOptions

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
    argv += ["--strategy", STRATEGY]
    argv += ["--execution", options.execution]
    if options.dry_run:
        argv.append("--dry-run")
    argv.append("--create-schema" if options.create_schema else "--no-create-schema")
    argv += ["--log-level", options.log_level]
    if options.show_data is True:
        argv.append("--show-data")
    elif options.show_data is False:
        argv.append("--no-data")
    else:
        argv += ["--sample", str(options.sample_size)]
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


# A quoted token (closed or still being typed) or a run of non-spaces.
_TOKEN_RE = re.compile(r'"[^"]*"?|\'[^\']*\'?|\S+')


def classify(text: str) -> List[Tuple[int, int, str]]:
    """Split a command line into ``(start, length, kind)`` spans for colouring.

    ``kind`` is ``"program"`` for a first token naming this program,
    ``"option"`` for a token starting with ``-``, and ``"value"`` otherwise.
    It tolerates half-typed text (an unclosed quote) because edit mode colours
    the command while it is being typed.
    """
    spans = []  # type: List[Tuple[int, int, str]]
    for index, match in enumerate(_TOKEN_RE.finditer(text)):
        token = match.group(0)
        if index == 0 and is_program_token(token):
            kind = "program"
        elif token.startswith("-"):
            kind = "option"
        else:
            kind = "value"
        spans.append((match.start(), match.end() - match.start(), kind))
    return spans


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
