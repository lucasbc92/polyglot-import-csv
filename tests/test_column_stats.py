"""Per-column type evidence must be accumulable chunk by chunk without changing a verdict.

`ColumnStats` is what lets a whole file be classified in bounded memory: each chunk
contributes counters and flags, and the merged counters decide the kind. Merging is
only sound if the verdict of the chunks equals the verdict of the whole column, so
these pin that equivalence on every kind, at several chunk sizes -- plus the one
rule that makes it possible, that digit-only values are never dates.

The cheap path stops each chunk at its own verdict, which can leave the merged date
bounds straddling the threshold (`decided()` is False). Exact updates close that gap.
"""

import pandas as pd
import pytest

from polyglotimportcsv import csv_reader
from polyglotimportcsv.csv_reader import ColumnStats, infer_column_kinds

BOOLS = ["true", "false", "TRUE", "False"] * 40
INTS = [str(n) for n in range(1000, 1150)]
FLOATS = [f"{n}.5" for n in range(150)]
ISO_DATES = [f"2023-{1 + n % 12:02d}-{1 + n % 28:02d}T00:00:00Z" for n in range(150)]
DATES_WITH_10PCT_JUNK = [
    f"2023-{1 + n % 12:02d}-{1 + n % 28:02d}T00:00:00Z" if n % 10 else f"junk-{n}"
    for n in range(150)
]
NAMES = [f"Product{n}" for n in range(150)]
DIGITS_THEN_TEXT = [str(n) for n in range(1000, 1150)] + ["X-1"]


def test_digit_only_values_never_count_as_dates():
    ids = [str(n) for n in range(1000, 1100)] + ["X-1"]
    assert infer_column_kinds(pd.DataFrame({"id": ids}))["id"] == "string"


@pytest.mark.parametrize("values,expected", [
    (BOOLS, "boolean"),
    (INTS, "integer"),
    (FLOATS, "float"),
    (ISO_DATES, "datetime"),
    (DATES_WITH_10PCT_JUNK, "datetime"),
    (NAMES, "string"),
    (DIGITS_THEN_TEXT, "string"),
])
@pytest.mark.parametrize("cut", [1, 7, 50])
def test_chunked_stats_match_the_whole_column(values, expected, cut):
    s = pd.Series(values, dtype=str)
    acc = ColumnStats()
    for start in range(0, len(s), cut):
        part = ColumnStats()
        part.update(s.iloc[start:start + cut])
        acc = acc.merged(part)
    assert acc.kind() == infer_column_kinds(pd.DataFrame({"c": s}))["c"] == expected


def test_a_late_non_boolean_value_breaks_boolean():
    a, b = ColumnStats(), ColumnStats()
    a.update(pd.Series(["true", "false"] * 50))
    b.update(pd.Series(["maybe"]))
    assert a.merged(b).kind() == "string"


def test_undecided_date_bounds_resolve_to_string():
    st = ColumnStats(
        non_empty=100, all_boolean=False, all_numeric=False, dates_min=80, dates_max=90
    )
    assert not st.decided()
    assert st.kind() == "string"


def test_empty_values_do_not_count():
    st = ColumnStats()
    st.update(pd.Series(["", "", ""]))
    assert st.non_empty == 0 and st.kind() == "empty"


def _accumulate(values, cut, **update_kwargs):
    s = pd.Series(values, dtype=str)
    acc = ColumnStats()
    for start in range(0, len(s), cut):
        part = ColumnStats()
        part.update(s.iloc[start:start + cut], **update_kwargs)
        acc = acc.merged(part)
    return acc


@pytest.fixture
def small_probe_rounds(monkeypatch):
    """Probe 50 distinct values per round, so the early stop bites on test-sized chunks."""
    monkeypatch.setattr(csv_reader, "_DATETIME_PROBE_CHUNK", 50)


#: 90% dates, but the first 300 values are junk: the first chunk is dirty, the rest clean.
DIRTY_BLOCK_THEN_DATES = ["n/a"] * 300 + (
    pd.date_range("2023-01-01", periods=2700, freq="min").strftime("%Y-%m-%dT%H:%M:%SZ").tolist()
)


def test_a_dirty_block_leaves_default_chunked_stats_undecided(small_probe_rounds):
    # Each clean chunk stops at its own verdict and keeps ~85% of itself as a lower
    # bound, so the dirty chunk drains the sum below the threshold of the whole column.
    acc = _accumulate(DIRTY_BLOCK_THEN_DATES, cut=500)
    assert acc.dates_min <= csv_reader._DATETIME_THRESHOLD * acc.non_empty < acc.dates_max
    assert not acc.decided()
    assert acc.kind() == "string"


def test_exact_updates_settle_a_dirty_block_column(small_probe_rounds):
    acc = _accumulate(DIRTY_BLOCK_THEN_DATES, cut=500, exact=True)
    whole = pd.DataFrame({"c": pd.Series(DIRTY_BLOCK_THEN_DATES, dtype=str)})
    assert acc.decided()
    assert acc.dates_min == acc.dates_max == 2700
    assert acc.kind() == infer_column_kinds(whole)["c"] == "datetime"


def test_exact_mode_probes_a_numeric_chunk_too():
    # "2023.5" is numeric and still parses as a date. The default update only bounds
    # such a chunk from above, which leaves this 90%-dates column undecided.
    numeric_dates = ["2023.5", "2023.01", "2020.12"] * 10
    values = numeric_dates + ISO_DATES[:60] + [f"junk-{n}" for n in range(10)]
    whole = pd.DataFrame({"c": pd.Series(values, dtype=str)})
    assert infer_column_kinds(whole)["c"] == "datetime"
    assert not _accumulate(values, cut=30).decided()
    acc = _accumulate(values, cut=30, exact=True)
    assert acc.decided() and acc.dates_min == acc.dates_max == 90
    assert acc.kind() == "datetime"


@pytest.mark.parametrize("values,expected", [(ISO_DATES, "datetime"), (NAMES, "string")])
def test_chunks_that_all_settle_the_same_way_are_decided(values, expected, small_probe_rounds):
    acc = _accumulate(values, cut=50)
    assert acc.decided()
    assert acc.kind() == expected


def test_object_columns_of_non_strings_are_still_classified():
    df = pd.DataFrame({
        "ints": pd.Series([1, 2, 3, 4], dtype=object),
        "bools": pd.Series([True, False, True], dtype=object),
    })
    assert infer_column_kinds(df) == {"ints": "integer", "bools": "boolean"}
