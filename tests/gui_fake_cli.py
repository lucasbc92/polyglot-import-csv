"""Stand-in for the real CLI, driven by the ImportProcess tests.

Usage: gui_fake_cli.py [exit_code] [--sleep]
"""

import sys
import time


def main() -> int:
    exit_code = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    sys.stdout.write("\x1b[32mok\x1b[0m primeira linha\n")
    sys.stdout.flush()
    sys.stdout.write("progresso 10%\rprogresso 90%\n")
    sys.stdout.flush()
    if "--sleep" in sys.argv:
        time.sleep(30)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
