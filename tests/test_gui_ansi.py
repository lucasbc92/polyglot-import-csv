"""ANSI -> HTML translation for the GUI console."""

from polyglotimportcsv.gui import ansi
from polyglotimportcsv.gui.ansi import AnsiRenderer, Style, apply_sgr, xterm256


def render_all(renderer):
    start, lines = renderer.take_update()
    assert start == 0
    return lines


def test_plain_text_becomes_one_line():
    r = AnsiRenderer()
    r.feed("ola mundo")
    assert render_all(r) == ["ola&nbsp;mundo"]


def test_newline_splits_lines():
    r = AnsiRenderer()
    r.feed("um\ndois\n")
    assert render_all(r) == ["um", "dois", "&nbsp;"]


def test_basic_foreground_colour():
    r = AnsiRenderer()
    r.feed("\x1b[32mok\x1b[0m!")
    assert render_all(r) == ['<span style="color:#1D8A46">ok</span>!']


def test_bright_foreground_and_bold():
    r = AnsiRenderer()
    r.feed("\x1b[1;94mx\x1b[0m")
    assert render_all(r) == ['<span style="color:#6EA8FE;font-weight:600">x</span>']


def test_background_colour():
    r = AnsiRenderer()
    r.feed("\x1b[41my\x1b[0m")
    assert render_all(r) == ['<span style="background-color:#D23A31">y</span>']


def test_truecolor_sequence():
    r = AnsiRenderer()
    r.feed("\x1b[38;2;16;32;48mz\x1b[0m")
    assert render_all(r) == ['<span style="color:#102030">z</span>']


def test_256_colour_sequence():
    r = AnsiRenderer()
    r.feed("\x1b[38;5;196mz\x1b[0m")
    assert render_all(r) == ['<span style="color:#FF0000">z</span>']


def test_xterm256_ranges():
    assert xterm256(1) == "#D23A31"
    assert xterm256(9) == "#F2736A"
    assert xterm256(16) == "#000000"
    assert xterm256(231) == "#FFFFFF"
    assert xterm256(232) == "#080808"


def test_reset_clears_every_attribute():
    assert apply_sgr(Style(fg="#fff", bg="#000", bold=True), [0]) == Style()


def test_sgr_39_and_49_clear_one_channel():
    assert apply_sgr(Style(fg="#fff", bg="#000"), [39]) == Style(bg="#000")
    assert apply_sgr(Style(fg="#fff", bg="#000"), [49]) == Style(fg="#fff")


def test_carriage_return_rewrites_the_current_line():
    r = AnsiRenderer()
    r.feed("10%\r90%")
    assert render_all(r) == ["90%"]


def test_cursor_up_plus_erase_rewrites_previous_lines():
    r = AnsiRenderer()
    r.feed("a\nb\n")
    render_all(r)
    r.feed("\x1b[2A\x1b[2Kc")
    start, lines = r.take_update()
    assert start == 0
    assert lines[0] == "c"


def test_cursor_visibility_sequences_are_ignored():
    r = AnsiRenderer()
    r.feed("\x1b[?25la\x1b[?25h")
    assert render_all(r) == ["a"]


def test_unknown_escape_is_dropped_without_eating_text():
    r = AnsiRenderer()
    r.feed("\x1b]0;titulo\x07texto")
    assert render_all(r) == ["texto"]


def test_sequence_split_across_chunks():
    r = AnsiRenderer()
    r.feed("\x1b[3")
    r.feed("2mok\x1b[0m")
    assert render_all(r) == ['<span style="color:#1D8A46">ok</span>']


def test_take_update_only_returns_changed_tail():
    r = AnsiRenderer()
    r.feed("a\nb\n")
    render_all(r)
    r.feed("c")
    start, lines = r.take_update()
    assert start == 2
    assert lines == ["c"]


def test_take_update_is_empty_when_nothing_changed():
    r = AnsiRenderer()
    r.feed("a")
    render_all(r)
    start, lines = r.take_update()
    assert lines == []


def test_buffer_is_trimmed_and_forces_a_full_repaint():
    r = AnsiRenderer(max_lines=3)
    r.feed("1\n2\n3\n4\n")
    start, lines = r.take_update()
    assert start == 0
    assert r.line_count == 3


def test_html_is_escaped():
    r = AnsiRenderer()
    r.feed("<b>&</b>")
    assert render_all(r) == ["&lt;b&gt;&amp;&lt;/b&gt;"]


def test_module_does_not_import_qt():
    source = open(ansi.__file__, encoding="utf-8").read()
    assert "PySide6" not in source
