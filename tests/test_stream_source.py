import pandas as pd
from polyglotimportcsv import stream_source as ss
from polyglotimportcsv.sources import SOURCE_COLUMN


def _write_csv(path, header, rows):
    path.write_text(",".join(header) + "\n" +
                    "\n".join(",".join(str(c) for c in r) for r in rows) + "\n",
                    encoding="utf-8")


def test_multi_yields_chunks_with_source_column(tmp_path):
    _write_csv(tmp_path / "a.csv", ["id", "v"], [(i, f"x{i}") for i in range(2500)])
    cfg = {"alpha": "a.csv"}
    chunks = list(ss.iter_entity_chunks(cfg, tmp_path, chunksize=1000))
    assert [name for name, _ in chunks] == ["alpha", "alpha", "alpha"]  # ceil(2500/1000)
    total = sum(len(df) for _, df in chunks)
    assert total == 2500
    first = chunks[0][1]
    assert SOURCE_COLUMN in first.columns
    assert (first[SOURCE_COLUMN] == "alpha").all()
    assert list(first.columns)[:2] == ["id", "v"]


def test_combined_routes_by_origin(tmp_path):
    rows = [("stock", i, f"s{i}") for i in range(10)] + [("cart", i, f"c{i}") for i in range(5)]
    _write_csv(tmp_path / "j.csv", ["action", "id", "v"], rows)
    cfg = {"ecom": {"file": "j.csv"}}
    chunks = list(ss.iter_entity_chunks(cfg, tmp_path, chunksize=1000))
    by_name = {}
    for name, df in chunks:
        by_name.setdefault(name, 0)
        by_name[name] += len(df)
    assert by_name == {"stock": 10, "cart": 5}
    # origin column dropped; data columns + _source present
    a_chunk = next(df for name, df in chunks if name == "stock")
    assert "action" not in a_chunk.columns
    assert list(a_chunk.columns)[:2] == ["id", "v"]
    assert (a_chunk[SOURCE_COLUMN] == "stock").all()
