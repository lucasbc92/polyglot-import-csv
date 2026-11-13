"""The automatic read-block rule (spec: "Resultado da campanha exploratória")."""

import json
from pathlib import Path

from polyglotimportcsv.auto_size import auto_chunk_mb, choose_chunk_mb
from polyglotimportcsv.stream_source import source_memory_mb


def test_whole_source_wins_when_memory_allows():  # 131072 rows on the campaign machine
    c = choose_chunk_mb(95.5, 29.9, 890.0)
    assert c.mb == 96  # rounded up, so the source fits in one block
    assert "largest source read whole (95.5 MB)" in c.reason
    assert "890 MB free" in c.reason


def test_free_memory_limits_the_block():  # 262144 rows on the campaign machine
    c = choose_chunk_mb(191.0, 60.3, 890.0)
    assert c.mb == 56
    assert "limited by free memory" in c.reason


def test_more_memory_reads_the_larger_source_whole():
    assert choose_chunk_mb(191.0, 60.3, 2048.0).mb == 191


def test_a_whole_source_block_is_rounded_up():
    # 17.91 MB rounded down to 17 read the source in two blocks (final review, etapa 2).
    assert choose_chunk_mb(17.91, 30.0, 890.0).mb == 18


def test_a_memory_limited_block_is_rounded_down():
    c = choose_chunk_mb(191.0, 60.3, 890.0)  # limit 56.6 MB
    assert c.mb == 56


def test_rounding_up_never_crosses_the_memory_limit():
    # whole 56.3 MB, limit 56.6 MB: 57 would exceed the limit, so the limit decides.
    c = choose_chunk_mb(56.3, 60.3, 890.0)
    assert c.mb == 56 and "limited by free memory" in c.reason


def test_source_larger_than_the_maximum_gets_256():
    c = choose_chunk_mb(400.0, 10.0, 16000.0)
    assert c.mb == 256
    assert "exceeds the 256 MB maximum" in c.reason


def test_unknown_free_memory_skips_the_limit():
    c = choose_chunk_mb(191.0, 60.3, None)
    assert c.mb == 191
    assert "free memory unknown" in c.reason


def test_starved_memory_still_gives_the_minimum():
    c = choose_chunk_mb(191.0, 60.3, 100.0)  # the safety limit is negative
    assert c.mb == 16
    assert "limited by free memory" in c.reason
    assert "16 MB minimum" in c.reason


def test_tiny_source_gets_the_minimum_block():
    assert choose_chunk_mb(0.0, 0.0, 890.0).mb == 16


def _csv(path: Path, rows: int) -> Path:
    lines = ["id,name,price"] + [f"{i},product number {i},{i * 1.5:.2f}" for i in range(rows)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _config(sources):
    return {
        "sources": sources,
        "postgres": {"entities": {"items": {"source": "src"}}},
    }


def test_auto_chunk_measures_the_override_file(tmp_path):
    _csv(tmp_path / "small.csv", 10)
    big = _csv(tmp_path / "big.csv", 20000)
    c = auto_chunk_mb(
        _config({"src": "small.csv"}), tmp_path, ["postgres"], {"src": str(big)}, 890.0
    )
    assert f"({source_memory_mb('src', big):.1f} MB)" in c.reason


def test_auto_chunk_reads_the_combined_file(tmp_path):
    join = tmp_path / "join.csv"
    lines = ["action,id,name"] + [f"src,{i},name {i}" for i in range(20000)]
    join.write_text("\n".join(lines) + "\n", encoding="utf-8")
    c = auto_chunk_mb(
        _config({"ecommerce": {"file": "join.csv"}}), tmp_path, ["postgres"], None, 890.0
    )
    assert f"({source_memory_mb('ecommerce', join):.1f} MB)" in c.reason


def test_auto_chunk_follows_the_largest_source_of_the_selected_dbms(tmp_path, monkeypatch):
    """The block reads the largest source whole, and the memory limit counts every
    source the import reads: both over the selected DBMS only."""
    from polyglotimportcsv import auto_size

    small = _csv(tmp_path / "small.csv", 10)
    big = _csv(tmp_path / "big.csv", 5000)
    _csv(tmp_path / "other.csv", 20000)  # read by a DBMS that is not selected
    config = {
        "sources": {"small": "small.csv", "big": "big.csv", "other": "other.csv"},
        "postgres": {"entities": {"a": {"source": "small"}, "b": {"source": "big"}}},
        "redis": {"entities": {"c": {"source": "other"}}},
    }
    seen = {}

    def choose(largest_source_mb, sources_disk_mb, free_mb):
        seen.update(largest=largest_source_mb, disk=sources_disk_mb, free=free_mb)
        return auto_size.AutoChunk(16, "spy")

    monkeypatch.setattr(auto_size, "choose_chunk_mb", choose)
    auto_chunk_mb(config, tmp_path, ["postgres"], None, 890.0)

    assert seen["largest"] == source_memory_mb("big", big) > source_memory_mb("small", small)
    assert seen["disk"] == (small.stat().st_size + big.stat().st_size) / 2**20
    assert seen["free"] == 890.0
