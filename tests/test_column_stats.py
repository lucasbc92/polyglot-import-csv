"""Per-column type evidence must be accumulable chunk by chunk without changing a verdict.

`ColumnStats` is what lets a whole file be classified in bounded memory: each chunk
contributes counters and flags, and the merged counters decide the kind. Merging is
only sound if the verdict of the chunks equals the verdict of the whole column, so
these pin that equivalence on every kind, at several chunk sizes -- plus the one
rule that makes it possible, that digit-only values are never dates.
"""

import pandas as pd
import pytest

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
    assert st.kind() == "string"


def test_empty_values_do_not_count():
    st = ColumnStats()
    st.update(pd.Series(["", "", ""]))
    assert st.non_empty == 0 and st.kind() == "empty"
