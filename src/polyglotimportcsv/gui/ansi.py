"""Translate the CLI's ANSI output into HTML lines for the console widget.

The renderer owns the console's line buffer and reports only the tail that
changed since the last read, which is what keeps rich's progress-bar redraws
(cursor-up + erase-line, many times a second) cheap to repaint.

Pure Python: no Qt.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, replace
from typing import List, Optional, Tuple

BASE_COLORS = (
    "#161A21", "#D23A31", "#1D8A46", "#C77B1F",
    "#2F6FE0", "#A05CC8", "#2AA1A8", "#D6DCE5",
)
BRIGHT_COLORS = (
    "#78839A", "#F2736A", "#57C77A", "#E7C267",
    "#6EA8FE", "#C89BEA", "#6FD5DB", "#FFFFFF",
)
CUBE_LEVELS = (0, 95, 135, 175, 215, 255)
DEFAULT_MAX_LINES = 5000
_MAX_PENDING = 4096  # bytes withheld while waiting for a split escape sequence

_CSI = re.compile(r"\x1b\[([0-9;?]*)([A-Za-z])")


@dataclass(frozen=True)
class Style:
    """Text attributes carried by one run of characters."""

    fg: Optional[str] = None
    bg: Optional[str] = None
    bold: bool = False


def _hexcolor(r: int, g: int, b: int) -> str:
    return "#{0:02X}{1:02X}{2:02X}".format(r, g, b)


def xterm256(index: int) -> str:
    """Map an xterm-256 colour index onto a hex colour."""
    if index < 8:
        return BASE_COLORS[index]
    if index < 16:
        return BRIGHT_COLORS[index - 8]
    if index < 232:
        n = index - 16
        return _hexcolor(CUBE_LEVELS[n // 36], CUBE_LEVELS[(n // 6) % 6], CUBE_LEVELS[n % 6])
    value = 8 + (index - 232) * 10
    return _hexcolor(value, value, value)


def apply_sgr(style: Style, params: List[int]) -> Style:
    """Apply one SGR parameter list to ``style``."""
    if not params:
        return Style()
    index = 0
    while index < len(params):
        code = params[index]
        if code == 0:
            style = Style()
        elif code == 1:
            style = replace(style, bold=True)
        elif code == 22:
            style = replace(style, bold=False)
        elif 30 <= code <= 37:
            style = replace(style, fg=BASE_COLORS[code - 30])
        elif 90 <= code <= 97:
            style = replace(style, fg=BRIGHT_COLORS[code - 90])
        elif 40 <= code <= 47:
            style = replace(style, bg=BASE_COLORS[code - 40])
        elif 100 <= code <= 107:
            style = replace(style, bg=BRIGHT_COLORS[code - 100])
        elif code == 39:
            style = replace(style, fg=None)
        elif code == 49:
            style = replace(style, bg=None)
        elif code in (38, 48) and index + 1 < len(params):
            mode = params[index + 1]
            if mode == 5 and index + 2 < len(params):
                color = xterm256(params[index + 2])
                index += 2
            elif mode == 2 and index + 4 < len(params):
                color = _hexcolor(params[index + 2], params[index + 3], params[index + 4])
                index += 4
            else:
                index += 1
                continue
            style = replace(style, fg=color) if code == 38 else replace(style, bg=color)
        index += 1
    return style


class AnsiRenderer(object):
    """Stateful translator from an ANSI byte stream to HTML console lines."""

    def __init__(self, max_lines: int = DEFAULT_MAX_LINES) -> None:
        self._max_lines = max_lines
        self._lines = [[]]  # type: List[List[Tuple[str, Style]]]
        self._row = 0
        self._style = Style()
        self._pending = ""
        self._dirty = 0

    @property
    def line_count(self) -> int:
        return len(self._lines)

    def feed(self, chunk: str) -> None:
        """Consume one decoded chunk of the child process's output."""
        data = self._pending + chunk
        self._pending = ""
        index = 0
        while index < len(data):
            char = data[index]
            if char == "\x1b":
                match = _CSI.match(data, index)
                if match is not None:
                    self._handle_csi(match.group(1), match.group(2))
                    index = match.end()
                    continue
                if self._is_incomplete_escape(data, index):
                    remainder = data[index:]
                    if len(remainder) <= _MAX_PENDING:
                        self._pending = remainder
                    # else: drop it — an unterminated escape this long will
                    # never be valid text anyway, and _pending must stay
                    # bounded rather than grow without limit.
                    return
                index = self._skip_unknown_escape(data, index)
                continue
            if char == "\n":
                self._newline()
                index += 1
                continue
            if char == "\r":
                # C1: on Windows every text line ends with "\r\n". Treating a
                # bare "\r" as an erase would wipe each line right after it was
                # written, leaving a console full of blank rows. Only a "\r"
                # that is NOT followed by "\n" is the carriage return rich uses
                # to redraw a progress line in place.
                if index + 1 >= len(data):
                    # The next character decides which of the two this is, and
                    # it has not arrived yet: withhold the "\r" rather than
                    # guess. _pending stays bounded — this adds one character.
                    self._pending = "\r"
                    return
                if data[index + 1] == "\n":
                    self._newline()
                    index += 2
                    continue
                self._clear_line()
                index += 1
                continue
            end = index
            while end < len(data) and data[end] not in "\x1b\n\r":
                end += 1
            self._write(data[index:end])
            index = end

    def take_update(self) -> Tuple[int, List[str]]:
        """Return the first changed line index and the HTML from there on."""
        first = min(self._dirty, len(self._lines))
        rendered = [self._render(line) for line in self._lines[first:]]
        self._dirty = len(self._lines)
        return first, rendered

    def flush(self) -> None:
        """Flush any buffered incomplete escape sequence as literal text.

        Call this once the child process has exited, so trailing output that
        was withheld while waiting for a possible continuation (e.g. a
        truncated escape sequence at end of stream) is not silently
        dropped. Task 9's ``ConsolePanel.flush_output()`` calls this when
        Task 10's ``MainWindow`` detects the child process has finished.
        """
        if not self._pending:
            return
        text = self._pending
        self._pending = ""
        if text == "\r":
            # C1: a trailing "\r" was withheld only to see whether a "\n"
            # would follow. The stream is over, so no "\n" ever will: it is
            # the redraw form, not a line ending, and it is not literal text.
            self._clear_line()
            return
        self._write(text)

    # -- internals --------------------------------------------------------

    @staticmethod
    def _is_incomplete_escape(data: str, index: int) -> bool:
        """Return True if the escape sequence starting at ``index`` cannot
        yet be classified because its terminator has not arrived.

        This is a real completeness test, not a length heuristic: a lone
        ESC, a CSI introducer followed only by parameter characters, or an
        OSC introducer with no BEL/ST terminator anywhere in ``data`` are
        all incomplete regardless of how many characters remain.
        """
        rest = data[index + 1:]
        if rest == "":
            return True
        introducer = rest[0]
        if introducer == "[":
            body = rest[1:]
            for ch in body:
                if ch.isalpha():
                    return False
                if ch not in "0123456789;?":
                    return False
            return True
        if introducer == "]":
            body = rest[1:]
            if "\x07" in body:
                return False
            if "\x1b\\" in body:
                return False
            return True
        return False

    @staticmethod
    def _skip_unknown_escape(data: str, index: int) -> int:
        """Drop an escape sequence we don't interpret, terminator included."""
        if data[index + 1:index + 2] == "]":
            # OSC: runs until BEL or ST (ESC \). Its payload can contain
            # letters, so we cannot stop at the first one.
            bel = data.find("\x07", index)
            st = data.find("\x1b\\", index)
            ends = [candidate for candidate in (bel, st) if candidate != -1]
            if not ends:
                return len(data)
            if st == -1 or (bel != -1 and bel < st):
                return bel + 1
            return st + 2
        return min(index + 2, len(data))

    def _handle_csi(self, params: str, final: str) -> None:
        if params.startswith("?"):
            return
        values = [int(part) for part in params.split(";") if part.isdigit()]
        if final == "m":
            self._style = apply_sgr(self._style, values)
        elif final == "A":
            self._cursor_up(values[0] if values else 1)
        elif final == "K":
            self._clear_line()

    def _write(self, text: str) -> None:
        if not text:
            return
        self._lines[self._row].append((text, self._style))
        self._touch(self._row)

    def _newline(self) -> None:
        if self._row == len(self._lines) - 1:
            self._lines.append([])
        self._row += 1
        self._touch(self._row)
        self._trim()

    def _clear_line(self) -> None:
        self._lines[self._row] = []
        self._touch(self._row)

    def _cursor_up(self, count: int) -> None:
        self._row = max(0, self._row - max(1, count))
        self._touch(self._row)

    def _touch(self, row: int) -> None:
        self._dirty = min(self._dirty, row)

    def _trim(self) -> None:
        excess = len(self._lines) - self._max_lines
        if excess <= 0:
            return
        del self._lines[:excess]
        self._row = max(0, self._row - excess)
        self._dirty = 0

    @staticmethod
    def _render(spans: List[Tuple[str, Style]]) -> str:
        parts = []
        for text, style in spans:
            escaped = html.escape(text).replace(" ", "&nbsp;")
            css = []
            if style.fg:
                css.append("color:" + style.fg)
            if style.bg:
                css.append("background-color:" + style.bg)
            if style.bold:
                css.append("font-weight:600")
            parts.append('<span style="{0}">{1}</span>'.format(";".join(css), escaped) if css else escaped)
        return "".join(parts) or "&nbsp;"
