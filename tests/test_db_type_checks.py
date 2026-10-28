"""Value checks against the declared DBMS type: PostgreSQL db_type and Cassandra CQL type."""

from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from polyglotimportcsv.db_type_checks import cassandra_value_problem, postgres_value_problem

NOW = datetime(2024, 1, 2, 3, 4, 5)
NAN = float("nan")
INF = float("inf")
REAL_MAX = 3.4028235e38


def _row_id(row):
    """``type-value type-value`` so int 32768, str "32768" and float 32768.0 differ in the report."""
    type_name, value, outcome = row
    shown = "()" if type(value) is object else repr(value)
    if len(shown) > 30:
        shown = shown[:27] + "..."
    if isinstance(outcome, bool):
        outcome = "ok" if outcome else "rejected"
    return f"{type_name}-{type(value).__name__}-{shown}-{outcome}"


def _ids(rows):
    return [_row_id(row) for row in rows]


_PG_INT_BITS = {"SMALLINT": 16, "INT2": 16, "INTEGER": 32, "INT": 32, "INT4": 32, "BIGINT": 64, "INT8": 64}

# Both edges of every integer base: 2**(b-1) - 1 and -2**(b-1) fit, one more does not.
_PG_INT_EDGES = [
    (base, value, ok)
    for base, bits in _PG_INT_BITS.items()
    for value, ok in (
        (2 ** (bits - 1) - 1, True),
        (2 ** (bits - 1), False),
        (-(2 ** (bits - 1)), True),
        (-(2 ** (bits - 1)) - 1, False),
    )
]

_PG_INT_ROWS = [
    # int (but never bool), float with is_integer(), str of digits
    (base, value, ok)
    for base in _PG_INT_BITS
    for value, ok in (
        (5, True), (0, True), (-7, True),
        (5.0, True), (-3.0, True),
        ("12", True), (" +7 ", True), ("-3", True), ("007", True),
        (True, False), (False, False),
        (NOW, False), (date(2024, 1, 2), False),
        (3.5, False), (NAN, False), (INF, False), (-INF, False),
        ("3.0", False), ("abc", False), ("", False), ("1e3", False), ("1_0", False), ("١٢", False),
        # NumPy scalars are judged like the Python type they stand for
        (np.int8(5), True), (np.int64(5), True), (np.float32(3.0), True),
        (np.float32(3.5), False), (np.bool_(True), False), (np.bool_(False), False),
        (np.datetime64("2024-01-02"), False),
    )
] + [
    ("SMALLINT", np.int32(32768), False), ("SMALLINT", np.int32(-32768), True),
    ("INTEGER", np.int64(2**31), False), ("INTEGER", np.int64(2**31 - 1), True),
    ("BIGINT", np.uint64(2**63), False), ("BIGINT", np.uint64(2**63 - 1), True),
    ("BIGINT", np.float64(2.0**63), False), ("BIGINT", np.float32(2.0**63), False),
    # a digit string is judged by its significant digits, never by converting a huge text
    ("BIGINT", "0" * 5000 + "1", True), ("BIGINT", "0" * 5000, True), ("BIGINT", " +" + "0" * 5000 + "7 ", True),
    ("BIGINT", "9" * 19, False), ("BIGINT", "9" * 20, False), ("BIGINT", "9" * 5000, False),
    ("BIGINT", "-" + "1" + "0" * 4999, False), ("BIGINT", "-" + "9" * 5000, False),
    ("BIGINT", "0" + str(2**63 - 1), True), ("BIGINT", "-0" + str(2**63), True),
    ("SMALLINT", "9" * 20, False), ("INTEGER", "9" * 5000, False), ("INTEGER", "0" * 5000 + "5", True),
] + [
    # the float and str forms obey the range too
    ("SMALLINT", 32768.0, False), ("SMALLINT", -32768.0, True), ("SMALLINT", "32768", False), ("SMALLINT", "-32768", True),
    ("INTEGER", float(2**31), False), ("INTEGER", -float(2**31), True), ("INTEGER", str(2**31), False),
    ("INTEGER", str(2**31 - 1), True),
    ("BIGINT", float(2**63), False), ("BIGINT", -float(2**63), True), ("BIGINT", str(2**63), False),
    ("BIGINT", str(-(2**63)), True), ("BIGINT", str(2**63 - 1), True), ("BIGINT", str(-(2**63) - 1), False),
    ("int4", 2**31, False), ("bigint", 5, True), (" bigint ", 5, True),
]

_PG_NUMERIC_BASES = ["NUMERIC", "DECIMAL", "REAL", "FLOAT4", "DOUBLE PRECISION", "FLOAT8", "FLOAT"]

_PG_NUMERIC_ROWS = [
    (base, value, ok)
    for base in _PG_NUMERIC_BASES
    for value, ok in (
        (5, True), (-2, True), (0, True), (1.5, True), (-0.25, True), (10**30, True),
        (REAL_MAX, True), (-REAL_MAX, True),
        (NAN, True), (INF, True), (-INF, True),
        ("1.5", True), (" 2 ", True), ("1e3", True), ("-7", True), ("inf", True), ("-Infinity", True), ("nan", True),
        (True, False), (False, False),
        (NOW, False), (date(2024, 1, 2), False),
        ("abc", False), ("", False), ("1,5", False),
        (np.int64(5), True), (np.float32(1.5), True), (np.float64(1.5), True),
        (np.bool_(True), False), (np.datetime64("2024-01-02"), False),
    )
] + [
    # REAL/FLOAT4 are 4-byte floats: a finite value beyond their range overflows; DOUBLE and unbounded NUMERIC do not
    (base, value, base not in ("REAL", "FLOAT4"))
    for base in _PG_NUMERIC_BASES
    for value in (1e39, -1e39, 1e40, 1e300, 10**39, "1e40", np.float64(1e40))
] + [
    ("REAL", REAL_MAX, True), ("REAL", -REAL_MAX, True), ("REAL", 3.4028236e38, False), ("REAL", -3.4028236e38, False),
    ("FLOAT4", REAL_MAX, True), ("FLOAT4", 3.4028236e38, False), ("FLOAT4", "-1e40", False),
    ("REAL", 10**400, False), ("REAL", -(10**400), False),
    ("REAL", np.float32(REAL_MAX), True), ("FLOAT4", np.float64(-1e40), False),
    ("REAL", INF, True), ("REAL", -INF, True), ("REAL", "inf", True), ("REAL", NAN, True),
    ("DOUBLE PRECISION", INF, True), ("DOUBLE PRECISION", "-Infinity", True), ("FLOAT8", "1e999", True),
    ("NUMERIC", "inf", True), ("NUMERIC", -INF, True), ("DECIMAL", "Infinity", True), ("NUMERIC", "1e999", True),
] + [
    # NUMERIC(p,s): the rounded absolute value must be < 10**(p - s)
    ("NUMERIC(14,2)", 999999999999.99, True),
    ("NUMERIC(14,2)", 1e12, False),
    ("NUMERIC(14,2)", 1e12 * 100, False),
    ("NUMERIC(14,2)", -999999999999.99, True),
    ("NUMERIC(14,2)", -1e12, False),
    ("NUMERIC(14,2)", 999999999999.996, False),
    ("NUMERIC(14,2)", 12, True),
    ("NUMERIC(14,2)", 10**12, False),
    ("NUMERIC(14,2)", "999999999999.99", True),
    ("NUMERIC(14,2)", "1000000000000", False),
    ("NUMERIC(5,2)", 999.99, True),
    ("NUMERIC(5,2)", 999.994, True),
    ("NUMERIC(5,2)", 999.995, False),
    ("NUMERIC(5,2)", 1000, False),
    ("NUMERIC(5,2)", 1000.0, False),
    ("NUMERIC(5,2)", "1000", False),
    ("NUMERIC(5,2)", "abc", False),
    ("NUMERIC(5,2)", True, False),
    ("NUMERIC(5,2)", np.int64(999), True),
    ("NUMERIC(5,2)", np.float32(1000.0), False),
    ("NUMERIC(5,2)", np.float64(1000.0), False),
    # NUMERIC(p,s) takes NaN but overflows on +-Infinity, in any spelling
    ("NUMERIC(5,2)", NAN, True),
    ("NUMERIC(5,2)", "nan", True),
    ("NUMERIC(5,2)", "NaN", True),
    ("NUMERIC(5,2)", INF, False),
    ("NUMERIC(5,2)", -INF, False),
    ("NUMERIC(5,2)", "inf", False),
    ("NUMERIC(5,2)", "+inf", False),
    ("NUMERIC(5,2)", "-inf", False),
    ("NUMERIC(5,2)", "Infinity", False),
    ("NUMERIC(5,2)", "-Infinity", False),
    ("NUMERIC(5,2)", " INFINITY ", False),
    ("NUMERIC(5,2)", "1e999", False),
    ("NUMERIC(5,2)", "-1e999", False),
    ("NUMERIC(5,2)", np.float32("inf"), False),
    ("NUMERIC(5)", INF, False),
    ("NUMERIC(5)", "-Infinity", False),
    ("DECIMAL(5,2)", INF, False),
    ("DECIMAL(5,2)", "Infinity", False),
    ("DECIMAL(5)", NAN, True),
    ("NUMERIC(14,2)", -INF, False),
    # scale defaults to 0; no parameters means no bound
    ("NUMERIC(5)", 99999, True),
    ("NUMERIC(5)", 99999.4, True),
    ("NUMERIC(5)", 100000, False),
    ("NUMERIC(5)", 99999.6, False),
    ("NUMERIC", 1e40, True),
    ("NUMERIC", 1e300, True),
    ("DECIMAL(5,2)", 999.99, True),
    ("DECIMAL(5,2)", 1000, False),
    ("DECIMAL(5)", 100000, False),
    ("numeric (5, 2)", 1000, False),
    ("numeric (5, 2)", 999.99, True),
    # only NUMERIC/DECIMAL take (p,s); FLOAT(n) is a bit precision
    ("FLOAT(53)", 1e40, True),
    ("FLOAT(53)", 1e300, True),
    ("DOUBLE PRECISION", 1e300, True),
    ("DOUBLE PRECISION", 1e40, True),
]

_PG_BOOLEAN_BASES = ["BOOLEAN", "BOOL"]

_PG_BOOLEAN_ROWS = [
    (base, value, ok)
    for base in _PG_BOOLEAN_BASES
    for value, ok in [(True, True), (False, True)]
    + [(word, True) for word in ("t", "true", "y", "yes", "on", "1", "f", "false", "n", "no", "off", "0")]
    + [("T", True), ("TRUE", True), ("Yes", True), ("OFF", True), (" yes ", True), ("\tFalse\n", True)]
    + [
        (1, False), (0, False), (2, False), (1.0, False), (0.0, False),
        (NOW, False), (date(2024, 1, 2), False),
        ("maybe", False), ("", False), ("2", False), ("tru", False), ("yes please", False), ("-1", False),
        (np.bool_(True), True), (np.bool_(False), True),
        (np.int64(1), False), (np.int8(0), False), (np.float32(1.0), False),
        (np.datetime64("2024-01-02"), False),
    ]
] + [("boolean", "YES", True), ("bool", 1, False)]

_PG_TIMESTAMP_BASES = [
    "TIMESTAMP", "TIMESTAMPTZ", "TIMESTAMP WITH TIME ZONE", "TIMESTAMP WITHOUT TIME ZONE", "DATE",
]

_PG_TIMESTAMP_ROWS = [
    (base, value, ok)
    for base in _PG_TIMESTAMP_BASES
    for value, ok in (
        (NOW, True), (date(2024, 1, 2), True), (pd.Timestamp("2024-01-02 03:04:05"), True),
        ("2024-01-02", True), ("2024-01-02 03:04:05", True), ("2024-01-02T03:04:05+00:00", True),
        ("31/12/2024", True), ("12/31/2024", True), ("Jan 5 2024", True),
        (5, False), (5.5, False), (True, False), (False, False),
        ("abc", False), ("", False), ("not a date", False),
        (np.datetime64("2024-01-02"), True), (np.datetime64("2024-01-02T03:04:05.123456789"), True),
        (np.int64(5), False), (np.float32(5.5), False), (np.bool_(True), False),
    )
] + [("timestamptz", NOW, True), ("timestamptz", 5, False), ("TIMESTAMP(3)", "2024-01-02", True)]

_PG_CHAR_BASES = ["VARCHAR", "CHARACTER VARYING", "CHAR", "CHARACTER"]

_PG_CHAR_ROWS = [
    (f"{base}(3)", value, ok)
    for base in _PG_CHAR_BASES
    for value, ok in (
        ("abc", True), ("ab", True), ("", True), ("abcd", False), ("abcdefghij", False),
        # PostgreSQL silently drops excess trailing spaces, and only spaces
        ("abc   ", True), ("   ", True), ("abcd ", False), (" abc", False), ("abc\t", False), ("ab \n", False),
        # an int is cast to text first; the other types are not checked
        (123, True), (12345, False), (0, True), (-12, True), (-123, False),
        (np.int64(123), True), (np.int64(12345), False), (np.str_("abcd"), False),
        (1.5, True), (12345.678, True), (True, True), (NOW, True), (date(2024, 1, 2), True),
        (np.float32(1.5), True), (np.bool_(True), True),
    )
] + [("varchar(3)", "abcd", False), ("VARCHAR(3)", "ábc", True), ("VARCHAR(3)", "ábcd", False),
     ("VARCHAR(3)", "abc" + " " * 100, True), ("VARCHAR(1)", 10, False), ("CHAR(2)", 10, True),
     ("VARCHAR", "x" * 10000, True), ("CHAR", "x" * 10000, True), ("VARCHAR", 10**30, True)]

# runs of whitespace in a type name count as one space
_PG_SPACED_ROWS = [
    ("DOUBLE  PRECISION", "abc", False), ("DOUBLE   PRECISION", 1.5, True), ("double\tprecision", "abc", False),
    ("  DOUBLE PRECISION  ", True, False),
    ("TIMESTAMP  WITH  TIME  ZONE", 5, False), ("TIMESTAMP   WITHOUT TIME ZONE", "abc", False),
    ("TIMESTAMP  WITH  TIME  ZONE", NOW, True),
    ("CHARACTER   VARYING(3)", "abcd", False), ("CHARACTER  VARYING (3)", "abc", True),
    ("CHARACTER  (3)", "abcd", False),
    ("NUMERIC ( 5 , 2 )", 1000, False), ("NUMERIC  (5,2)", 999.99, True),
]

# types the table does not cover are not checked
_PG_UNCHECKED_ROWS = [
    (db_type, value, True)
    for db_type in ("TEXT", "JSONB", "UUID", "BYTEA", "SOMETHING_ELSE")
    for value in (object(), "anything", 5, 2**200, 1.5, NAN, True, NOW, "")
]

# None is always accepted
_PG_NONE_ROWS = [
    (db_type, None, True)
    for db_type in (
        "BIGINT", "SMALLINT", "INTEGER", "NUMERIC(14,2)", "DOUBLE PRECISION", "REAL", "BOOLEAN",
        "TIMESTAMPTZ", "DATE", "VARCHAR(3)", "CHAR(1)", "TEXT", "JSONB",
    )
]


_PG_ROWS = (
    _PG_INT_EDGES + _PG_INT_ROWS + _PG_NUMERIC_ROWS + _PG_BOOLEAN_ROWS + _PG_TIMESTAMP_ROWS
    + _PG_CHAR_ROWS + _PG_SPACED_ROWS + _PG_UNCHECKED_ROWS + _PG_NONE_ROWS
)


@pytest.mark.parametrize("db_type,value,ok", _PG_ROWS, ids=_ids(_PG_ROWS))
def test_postgres_value_problem(db_type, value, ok):
    assert (postgres_value_problem(db_type, value) is None) is ok


_PG_REASONS = [
    ("BIGINT", 2**63, "out of BIGINT range"),
    ("int4", 2**31, "out of INT4 range"),
    ("SMALLINT", -32769, "out of SMALLINT range"),
    ("BIGINT", 3.5, "not an integer"),
    ("BIGINT", True, "not an integer"),
    ("BIGINT", "3.0", "not an integer"),
    ("NUMERIC(14,2)", 1e12, "out of NUMERIC(14,2) range"),
    ("NUMERIC(5)", 100000, "out of NUMERIC(5,0) range"),
    ("REAL", "abc", "not a number"),
    ("DOUBLE PRECISION", True, "not a number"),
    ("BOOLEAN", 1, "not a boolean"),
    ("BOOLEAN", "maybe", "not a boolean"),
    ("TIMESTAMPTZ", "abc", "not a date/time"),
    ("DATE", 5, "not a date/time"),
    ("VARCHAR(3)", "abcd", "longer than VARCHAR(3)"),
    ("character varying(2)", "abc", "longer than CHARACTER VARYING(2)"),
    ("BIGINT", "9" * 5000, "out of BIGINT range"),
    ("SMALLINT", "9" * 20, "out of SMALLINT range"),
    ("NUMERIC(5,2)", INF, "out of NUMERIC(5,2) range"),
    ("NUMERIC(5,2)", "-Infinity", "out of NUMERIC(5,2) range"),
    ("REAL", 1e40, "out of REAL range"),
    ("FLOAT4", -1e40, "out of FLOAT4 range"),
    ("REAL", "1e40", "out of REAL range"),
    ("VARCHAR(3)", 12345, "longer than VARCHAR(3)"),
    ("VARCHAR(3)", "abcd ", "longer than VARCHAR(3)"),
    ("DOUBLE  PRECISION", "abc", "not a number"),
    ("DATE", True, "not a date/time"),
    ("BIGINT", np.bool_(True), "not an integer"),
]


@pytest.mark.parametrize("db_type,value,reason", _PG_REASONS, ids=_ids(_PG_REASONS))
def test_postgres_value_problem_reason(db_type, value, reason):
    assert postgres_value_problem(db_type, value) == reason


_CQL_BIGINT_ROWS = [
    ("bigint", value, ok)
    for value, ok in (
        (5, True), (0, True), (-7, True),
        (2**63 - 1, True), (2**63, False), (-(2**63), True), (-(2**63) - 1, False),
        (True, False), (False, False),
        (5.0, False), (3.5, False), (NAN, False),
        ("12", False), ("", False),
        (NOW, False), (date(2024, 1, 2), False),
        # NumPy scalars are judged like the Python type they stand for
        (np.int8(5), True), (np.int64(5), True), (np.int64(2**63 - 1), True), (np.uint64(2**63), False),
        (np.float32(5.0), False), (np.float64(5.0), False), (np.bool_(True), False),
        (np.datetime64("2024-01-02"), False),
    )
]

_CQL_DOUBLE_ROWS = [
    ("double", value, ok)
    for value, ok in (
        (5, True), (-2, True), (1.5, True), (10**30, True), (NAN, True), (INF, True),
        (True, False), (False, False),
        ("1.5", False), ("", False),
        (NOW, False), (date(2024, 1, 2), False),
        (np.int32(5), True), (np.float32(1.5), True), (np.float64(1.5), True),
        (np.bool_(True), False), (np.datetime64("2024-01-02"), False),
    )
]

_CQL_BOOLEAN_ROWS = [
    ("boolean", value, ok)
    for value, ok in (
        (True, True), (False, True),
        (1, False), (0, False), (1.0, False),
        ("true", False), ("false", False), ("", False),
        (NOW, False),
        (np.bool_(True), True), (np.bool_(False), True),
        (np.int64(1), False), (np.float32(1.0), False), (np.datetime64("2024-01-02"), False),
    )
]

_CQL_TIMESTAMP_ROWS = [
    ("timestamp", value, ok)
    for value, ok in (
        (NOW, True), (date(2024, 1, 2), True), (1704164645000, True), (1.7e12, True), (0, True),
        ("2024-01-02", False), ("", False),
        (True, False), (False, False),
        (np.datetime64("2024-01-02"), True), (np.datetime64("2024-01-02T03:04:05.123456789"), True),
        (np.int64(1704164645000), True), (np.float32(1.5), True),
        (np.bool_(True), False), (np.bool_(False), False),
    )
]

_CQL_TEXT_ROWS = [
    ("text", value, True)
    for value in (
        "abc", "", 5, 2**200, 1.5, NAN, True, False, NOW, date(2024, 1, 2), object(),
        np.int64(1), np.float32(1.5), np.bool_(True), np.datetime64("2024-01-02"),
    )
]

# None is always accepted; types outside the table are not checked
_CQL_OTHER_ROWS = [
    (cql_type, None, True) for cql_type in ("text", "bigint", "double", "boolean", "timestamp")
] + [("uuid", "anything", True), ("int", "anything", True)]

_CQL_UPPER_ROWS = [("BIGINT", 2**63, False), ("Boolean", 1, False), ("DOUBLE", "x", False), ("TIMESTAMP", NOW, True)]


_CQL_ROWS = (
    _CQL_BIGINT_ROWS + _CQL_DOUBLE_ROWS + _CQL_BOOLEAN_ROWS + _CQL_TIMESTAMP_ROWS + _CQL_TEXT_ROWS
    + _CQL_OTHER_ROWS + _CQL_UPPER_ROWS
)


@pytest.mark.parametrize("cql_type,value,ok", _CQL_ROWS, ids=_ids(_CQL_ROWS))
def test_cassandra_value_problem(cql_type, value, ok):
    assert (cassandra_value_problem(cql_type, value) is None) is ok


_CQL_REASONS = [
    ("bigint", 2**63, "out of bigint range"),
    ("bigint", -(2**63) - 1, "out of bigint range"),
    ("bigint", 5.0, "not an integer"),
    ("bigint", True, "not an integer"),
    ("bigint", "12", "not an integer"),
    ("double", "1.5", "not a number"),
    ("double", True, "not a number"),
    ("boolean", "true", "not a boolean"),
    ("boolean", 1, "not a boolean"),
    ("timestamp", "2024-01-02", "not a date, datetime or number"),
    ("timestamp", True, "not a date, datetime or number"),
    ("bigint", np.bool_(True), "not an integer"),
    ("bigint", np.uint64(2**63), "out of bigint range"),
]


@pytest.mark.parametrize("cql_type,value,reason", _CQL_REASONS, ids=_ids(_CQL_REASONS))
def test_cassandra_value_problem_reason(cql_type, value, reason):
    assert cassandra_value_problem(cql_type, value) == reason


def test_cassandra_types_match_the_importer_mapping():
    """The CQL names this module checks are the ones the importer creates."""
    from polyglotimportcsv.importers.cassandra_importer import _cassandra_type_for

    created = {
        _cassandra_type_for({}, kind) for kind in ("integer", "float", "datetime", "boolean", "string")
    }
    assert created == {"bigint", "double", "timestamp", "boolean", "text"}
    # each created type has a rule: a value of the wrong kind is refused (text takes anything)
    wrong = {"bigint": "x", "double": "x", "timestamp": "x", "boolean": 1}
    for cql_type, value in wrong.items():
        assert cassandra_value_problem(cql_type, value) is not None
    assert cassandra_value_problem("text", object()) is None
