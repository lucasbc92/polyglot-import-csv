"""Per-entity data display for the streaming path."""

import logging

import pandas as pd

from polyglotimportcsv import reporting
from polyglotimportcsv.data_preview import StreamDataPreview


def _frame(start, count):
    return pd.DataFrame({"id": range(start, start + count)})


def test_sample_keeps_the_first_rows_and_reports_the_total(capsys):
    reporting.setup_reporting(logging.INFO, no_log=True)
    preview = StreamDataPreview(sample_size=3)
    preview.observe("postgres", "items", _frame(0, 2))
    preview.observe("postgres", "items", _frame(2, 5))
    assert capsys.readouterr().out == "", "the sample is printed at the end, not per batch"
    preview.finish()
    out = capsys.readouterr().out
    assert "postgres · items" in out
    assert "3 of 7 row(s)" in out
    assert '"id": 2' in out and '"id": 3' not in out


def test_sample_spans_batches_and_counts_every_row(capsys):
    reporting.setup_reporting(logging.INFO, no_log=True)
    preview = StreamDataPreview(sample_size=1500)
    for start in (0, 1000, 2000):
        preview.observe("postgres", "items", _frame(start, min(1000, 2500 - start)))
    preview.finish()
    out = capsys.readouterr().out
    assert "1500 of 2500 row(s)" in out
    assert "[1500]" in out and "[1501]" not in out


def test_sample_never_holds_more_than_n_rows():
    preview = StreamDataPreview(sample_size=4)
    for start in range(0, 100, 10):
        preview.observe("redis", "cart", _frame(start, 10))
    kept = sum(len(part) for part in preview._samples[("redis", "cart")])
    assert kept == 4


def test_small_entity_is_shown_whole_without_a_total(capsys):
    reporting.setup_reporting(logging.INFO, no_log=True)
    preview = StreamDataPreview(sample_size=50)
    preview.observe("mongodb", "catalog", _frame(0, 2))
    preview.finish()
    out = capsys.readouterr().out
    assert "mongodb · catalog: 2 row(s)" in out
    assert " of " not in out


def test_partitions_are_reported_in_the_order_they_were_first_written(capsys):
    reporting.setup_reporting(logging.INFO, no_log=True)
    preview = StreamDataPreview()
    preview.observe("postgres", "b", _frame(0, 1))
    preview.observe("postgres", "a", _frame(0, 1))
    preview.finish()
    out = capsys.readouterr().out
    assert out.index("postgres · b") < out.index("postgres · a")


def test_show_all_prints_each_batch_as_it_arrives(capsys):
    reporting.setup_reporting(logging.INFO, no_log=True)
    preview = StreamDataPreview(show_data=True)
    preview.observe("postgres", "items", _frame(0, 2))
    first = capsys.readouterr().out
    assert "postgres · items" in first and "[2]" in first
    preview.observe("postgres", "items", _frame(2, 2))
    second = capsys.readouterr().out
    assert "[3]" in second and "[4]" in second
    assert "postgres · items" not in second, "the header is printed once"
    preview.finish()
    assert capsys.readouterr().out == ""


def test_no_data_prints_nothing(capsys):
    reporting.setup_reporting(logging.INFO, no_log=True)
    preview = StreamDataPreview(show_data=False)
    preview.observe("postgres", "items", _frame(0, 5))
    preview.finish()
    assert capsys.readouterr().out == ""
