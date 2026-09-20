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


# -- fix round 1: incomplete-escape detection must be a real completeness
# test, not a fixed-length heuristic (I1/I2/I3) --------------------------


def test_combined_truecolor_split_across_chunks_mid_params():
    # 36-char combined fg+bg truecolor SGR, exactly what rich emits. The old
    # "< 16 chars remaining" heuristic let a split past offset 16 fall
    # through to _skip_unknown_escape and corrupt the line.
    seq = "\x1b[38;2;255;255;255;48;2;0;0;0mOK\x1b[0m"
    r = AnsiRenderer()
    r.feed(seq[:20])
    r.feed(seq[20:])
    assert render_all(r) == ['<span style="color:#FFFFFF;background-color:#000000">OK</span>']


def test_osc_split_across_chunks_past_old_threshold():
    osc = "\x1b]0;um titulo bem longo de janela\x07texto"
    r = AnsiRenderer()
    r.feed(osc[:20])
    r.feed(osc[20:])
    assert render_all(r) == ["texto"]


def test_short_osc_is_dropped_without_eating_text():
    # Well under any length threshold: this must not depend on how many
    # characters happen to be in the buffer.
    r = AnsiRenderer()
    r.feed("\x1b]0;t\x07texto")
    assert render_all(r) == ["texto"]


def test_osc_split_across_two_feed_calls():
    r = AnsiRenderer()
    r.feed("\x1b]0;um titulo bem longo de janela")
    r.feed("\x07texto")
    assert render_all(r) == ["texto"]


def test_osc_terminated_by_st_is_dropped():
    # ST (ESC \) is a valid OSC terminator alongside BEL.
    r = AnsiRenderer()
    r.feed("\x1b]0;titulo\x1b\\texto")
    assert render_all(r) == ["texto"]


def test_overlong_incomplete_escape_is_dropped_and_does_not_corrupt_next_text():
    # A CSI that never terminates must not grow _pending without bound; past
    # the cap it is dropped so later text renders cleanly.
    r = AnsiRenderer()
    r.feed("\x1b[" + ";" * 5000)
    r.feed("hello")
    assert render_all(r) == ["hello"]


# -- fix round 1: flush() surfaces trailing pending bytes at process exit
# (I4) --------------------------------------------------------------------


def test_flush_writes_pending_incomplete_escape_as_literal_text():
    r = AnsiRenderer()
    r.feed("fim\x1b[3")
    assert render_all(r) == ["fim"]
    r.flush()
    start, lines = r.take_update()
    assert start == 0
    assert lines == ["fim\x1b[3"]


def test_flush_is_a_no_op_when_nothing_is_pending():
    r = AnsiRenderer()
    r.feed("fim")
    render_all(r)
    r.flush()
    start, lines = r.take_update()
    assert lines == []


# -- fix round 2 (C1): "\r\n" is a line ending, not an erase ----------------


def test_crlf_renders_exactly_like_lf():
    crlf = AnsiRenderer()
    crlf.feed("linha A\r\nlinha B\r\n")
    lf = AnsiRenderer()
    lf.feed("linha A\nlinha B\n")
    rendered = render_all(crlf)
    assert rendered == render_all(lf)
    # Not a vacuous comparison: both sides must carry the real text.
    assert "linha&nbsp;A" in rendered


def test_crlf_does_not_blank_the_lines_it_terminates():
    r = AnsiRenderer()
    r.feed("linha A\r\nlinha B\r\n")
    assert render_all(r) == ["linha&nbsp;A", "linha&nbsp;B", "&nbsp;"]


def test_lone_carriage_return_still_redraws_the_current_line():
    # rich's progress bar redraws in place with a bare "\r": that behaviour
    # must survive the CRLF fix untouched.
    r = AnsiRenderer()
    r.feed("progresso 10%\rprogresso 90%\n")
    assert render_all(r) == ["progresso&nbsp;90%", "&nbsp;"]


def test_carriage_return_at_a_chunk_boundary_is_withheld_until_decided():
    # The OS splits a pipe read wherever it likes; a "\r" that lands last in
    # one chunk cannot be classified until the next character arrives.
    r = AnsiRenderer()
    r.feed("linha A\r")
    r.feed("\nlinha B\r\n")
    assert render_all(r) == ["linha&nbsp;A", "linha&nbsp;B", "&nbsp;"]


def test_carriage_return_at_a_chunk_boundary_still_erases_when_no_newline_follows():
    r = AnsiRenderer()
    r.feed("progresso 10%\r")
    r.feed("progresso 90%\n")
    assert render_all(r) == ["progresso&nbsp;90%", "&nbsp;"]


def test_double_carriage_return_before_a_newline_erases_then_breaks():
    r = AnsiRenderer()
    r.feed("linha A\r\r\nlinha B")
    assert render_all(r) == ["&nbsp;", "linha&nbsp;B"]


def test_trailing_carriage_return_at_end_of_stream_erases_on_flush():
    r = AnsiRenderer()
    r.feed("linha A\r")
    assert render_all(r) == ["linha&nbsp;A"]
    r.flush()
    start, lines = r.take_update()
    assert start == 0
    assert lines == ["&nbsp;"]
