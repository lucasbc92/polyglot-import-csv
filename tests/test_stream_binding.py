import pandas as pd
from polyglotimportcsv import stream_binding as sb
from polyglotimportcsv.sources import SOURCE_COLUMN


def test_binding_infers_kinds_and_respects_declared_db_type():
    sample = pd.DataFrame({"id": ["1", "2"], "when": ["2023-01-01", "2023-01-02"],
                           SOURCE_COLUMN: ["e", "e"]})
    ecfg = {"source": "e", "columns": {"id": {"db_type": "TEXT"}}}  # declared TEXT wins
    b = sb.bind_entity_from_sample("e", ecfg, sample, "e")
    assert b.kinds["when"] == "datetime"        # inferred
    assert b.cfg["columns"]["id"]["db_type"] == "TEXT"   # declared preserved
    assert b.kinds[SOURCE_COLUMN] == "string"
