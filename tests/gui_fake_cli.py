"""Stand-in for the real CLI, driven by the ImportProcess tests.

Usage: gui_fake_cli.py [exit_code] [--sleep]

Line endings are genuine CRLF, because that is what a Python child process
writes on Windows — the platform the GUI is built and defended on. C1 was a
renderer bug that a fabricated LF-only fake CLI hid completely.
"""

import sys
import time


def main() -> int:
    exit_code = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    # Write bytes directly so the line endings are CRLF on every platform,
    # instead of depending on the host's text-mode newline translation.
    out = sys.stdout.buffer
    out.write(b"\x1b[32mok\x1b[0m primeira linha\r\n")
    out.flush()
    out.write(b"progresso 10%\rprogresso 90%\r\n")
    out.flush()
    out.write(b"segunda linha\r\n")
    out.flush()
    if "--sleep" in sys.argv:
        time.sleep(30)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
