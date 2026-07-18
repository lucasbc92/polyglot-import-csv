"""csv_columns tokens: names, 1-based indices, ranges, mixed and overlapping."""

import pytest

from polyglotimportcsv.business_exception import MappingError
from polyglotimportcsv.column_selector import select_columns

HEADER = ["a", "b", "c", "d", "e"]


def test_range_is_one_based_inclusive():
    assert select_columns(["1-3"], HEADER) == ["a", "b", "c"]


def test_mixed_tokens_and_integer_index():
    # JSON integers and strings are both accepted; duplicates collapse.
    assert select_columns(["2-3", "e", 1, "b"], HEADER) == ["a", "b", "c", "e"]


def test_result_keeps_header_order():
    assert select_columns(["e", "a"], HEADER) == ["a", "e"]


@pytest.mark.parametrize("token", ["0", "6", "0-2", "4-9", "3-2"])
def test_out_of_bounds_raises_mapping_error(token):
    with pytest.raises(MappingError):
        select_columns([token], HEADER)


def test_unknown_name_raises_with_context():
    with pytest.raises(MappingError, match="entity 'x'"):
        select_columns(["nope"], HEADER, context="entity 'x'")
