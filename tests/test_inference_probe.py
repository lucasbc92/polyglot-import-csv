"""The datetime probe must be an optimization, never a reclassification.

`_exceeds_datetime_share` replaces "parse every row, then compare the parsed share
against the threshold" with a de-duplicated, early-exiting probe. It decides what
gets cast to timestamps and written to the databases, so the reductions have to be
exact -- especially around the threshold, and especially when the most frequent
values disagree with the column as a whole (the probe visits them first).
"""

import warnings

import pandas as pd
import pytest

from polyglotimportcsv.casting import is_boolean_series
from polyglotimportcsv.csv_reader import _DATETIME_THRESHOLD, _exceeds_datetime_share

_DATE = "2023-11-01T00:00:00Z"
_NOT_A_DATE = "Product1234"


def _naive_exceeds(s: pd.Series, threshold: float) -> bool:
    """The definition being optimized: parse everything, compare the share."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        parsed = pd.to_datetime(s, errors="coerce", utc=True)
    return bool(parsed.notna().mean() > threshold)


def _mixed(n_dates: int, n_other: int) -> pd.Series:
    return pd.Series(
        [f"2023-11-{1 + (i % 28):02d}T00:00:00Z" for i in range(n_dates)]
        + [f"item-{i}" for i in range(n_other)],
        dtype=object,
    )


@pytest.mark.parametrize("n_dates,n_other", [
    (100, 0),     # all dates
    (0, 100),     # no dates
    (86, 14),     # just over the 0.85 threshold
    (85, 15),     # exactly at it -- must be False, the comparison is strict >
    (84, 16),     # just under
    (900, 100),   # 0.90
    (1, 999),     # a lone date
])
def test_probe_matches_the_naive_share(n_dates, n_other):
    s = _mixed(n_dates, n_other)
    assert _exceeds_datetime_share(s, _DATETIME_THRESHOLD) == _naive_exceeds(
        s, _DATETIME_THRESHOLD
    )


def test_duplicates_are_weighted_by_their_counts():
    # One distinct date repeated 90x vs 10 distinct non-dates: de-duplicating must
    # not turn a 90%-dates column into a 1-of-11 minority.
    s = pd.Series([_DATE] * 90 + [f"x{i}" for i in range(10)], dtype=object)
    assert _exceeds_datetime_share(s, _DATETIME_THRESHOLD) is True
    assert _naive_exceeds(s, _DATETIME_THRESHOLD) is True


def test_most_frequent_value_disagreeing_with_the_column_does_not_decide_it():
    # The probe visits most-frequent-first. The single most common value here is
    # NOT a date (14% of rows), but 86% of rows are -- it must not bail early.
    s = pd.Series([_NOT_A_DATE] * 14 + [f"2023-11-{1 + i % 28:02d}T0{i % 10}:00:00Z"
                                        for i in range(86)], dtype=object)
    assert _exceeds_datetime_share(s, _DATETIME_THRESHOLD) is True
    assert _naive_exceeds(s, _DATETIME_THRESHOLD) is True


def test_probe_stops_early_on_a_column_that_is_plainly_not_dates():
    # 200k rows of one repeated non-date: the verdict must not cost 200k parses.
    s = pd.Series([_NOT_A_DATE] * 200_000, dtype=object)
    assert _exceeds_datetime_share(s, _DATETIME_THRESHOLD) is False


def test_empty_input_is_not_datetime():
    assert _exceeds_datetime_share(pd.Series([], dtype=object), _DATETIME_THRESHOLD) is False


@pytest.mark.parametrize("values,expected", [
    (["true", "false", "TRUE"], True),
    (["true", "  False  "], True),
    (["true", "yes"], False),
    (["Product1", "true"], False),   # decided by the first value
    ([], False),
])
def test_is_boolean_series_unchanged(values, expected):
    assert is_boolean_series(pd.Series(values, dtype=object)) is expected


def test_is_boolean_series_does_not_consume_the_whole_column():
    """A non-boolean first value settles it -- the generator must not be drained."""
    consumed = []

    def values():
        for v in ["Product1"] + [f"x{i}" for i in range(10_000)]:
            consumed.append(v)
            yield v

    assert is_boolean_series(values()) is False
    assert len(consumed) == 1
