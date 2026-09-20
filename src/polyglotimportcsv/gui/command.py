"""Turn the form state into the CLI argv, and into the text the panel shows.

Only options that differ from the CLI's own defaults are emitted, so the
displayed command stays as short as what a person would actually type.
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
    if options.strategy != "optimized":
        argv += ["--strategy", options.strategy]
    if options.execution != "stream":
        argv += ["--execution", options.execution]
    if options.dry_run:
        argv.append("--dry-run")
    if not options.create_schema:
        argv.append("--no-create-schema")
    if options.benchmark:
        argv.append("--benchmark")
    if options.log_level != "INFO":
        argv += ["--log-level", options.log_level]
    if options.show_data is True:
        argv.append("--show-data")
    elif options.show_data is False:
        argv.append("--no-data")
    for name, path in options.sources:
        argv += ["--source", "{0}={1}".format(name, path)]
    return argv


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
