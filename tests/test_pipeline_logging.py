"""Spec §4.2: DEBUG inference/mapping decisions; WARNING empty sources and text fallbacks."""

import logging

import pandas as pd

from polyglotimportcsv.casting import cast_frame
from polyglotimportcsv.mapping_resolver import resolve_backend_entities
from polyglotimportcsv.sources import load_sources


def test_load_sources_logs_kinds_and_warns_on_empty(tmp_path, caplog):
    (tmp_path / "empty.csv").write_text("id,name\n", encoding="utf-8")
    with caplog.at_level(logging.DEBUG, logger="polyglotimportcsv.sources"):
        load_sources({"empty": "empty.csv"}, tmp_path)
    assert any(
        r.levelno == logging.WARNING and "0 row(s)" in r.message for r in caplog.records
    )
    assert any("inferred kinds" in r.message for r in caplog.records)


def test_resolver_logs_effective_mapping_per_column(tmp_path, caplog):
    (tmp_path / "stock.csv").write_text("sku,qty\nA,5\n", encoding="utf-8")
    sources = load_sources({"stock": "stock.csv"}, tmp_path)
    bcfg = {"entities": {"stock": {}}}
    with caplog.at_level(logging.DEBUG, logger="polyglotimportcsv.mapping_resolver"):
        resolve_backend_entities(bcfg, sources)
    debug = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("sku" in m and "db_type" in m for m in debug)
    assert any("qty" in m and "BIGINT" in m for m in debug)


def test_cast_frame_warns_on_text_fallback(caplog):
    df = pd.DataFrame({"n": ["1", "x", "3"]})
    with caplog.at_level(logging.DEBUG, logger="polyglotimportcsv.casting"):
        out = cast_frame(df, {"n": "integer"})
    assert list(out["n"]) == [1, "x", 3]
    assert any(
        r.levelno == logging.WARNING and "could not be cast" in r.message
        for r in caplog.records
    )
