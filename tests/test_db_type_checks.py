"""Value checks against the declared DBMS type: PostgreSQL db_type and Cassandra CQL type."""

from datetime import date, datetime
from itertools import product

import pytest

from polyglotimportcsv.db_type_checks import cassandra_value_problem, postgres_value_problem

NOW = datetime(2024, 1, 2, 3, 4, 5)
NAN = float("nan")
INF = float("inf")

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
        (NOW, False),
        (3.5, False), (NAN, False), (INF, False), (-INF, False),
        ("3.0", False), ("abc", False), ("", False), ("1e3", False), ("1_0", False), ("١٢", False),
    )
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
        (5, True), (-2, True), (0, True), (1.5, True), (-0.25, True), (10**30, True), (1e300, True),
        (NAN, True), (INF, True), (-INF, True),
        ("1.5", True), (" 2 ", True), ("1e3", True), ("-7", True),
        (True, False), (False, False),
        (NOW, False),
        ("abc", False), ("", False), ("1,5", False),
    )
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
    # NaN and infinity are not bounded by NUMERIC(p,s)
    ("NUMERIC(5,2)", NAN, True),
    ("NUMERIC(5,2)", INF, True),
    ("NUMERIC(5,2)", -INF, True),
    # scale defaults to 0; no parameters means no bound
    ("NUMERIC(5)", 99999, True),
    ("NUMERIC(5)", 99999.4, True),
    ("NUMERIC(5)", 100000, False),
    ("NUMERIC(5)", 99999.6, False),
    ("NUMERIC", 1e40, True),
    ("DECIMAL(5,2)", 999.99, True),
    ("DECIMAL(5,2)", 1000, False),
    ("DECIMAL(5)", 100000, False),
    ("numeric (5, 2)", 1000, False),
    ("numeric (5, 2)", 999.99, True),
    # only NUMERIC/DECIMAL take (p,s); FLOAT(n) is a bit precision
    ("FLOAT(53)", 1e40, True),
    ("REAL", 1e40, True),
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
        (NOW, False),
        ("maybe", False), ("", False), ("2", False), ("tru", False), ("yes please", False), ("-1", False),
    ]
] + [("boolean", "YES", True), ("bool", 1, False)]

_PG_TIMESTAMP_BASES = [
    "TIMESTAMP", "TIMESTAMPTZ", "TIMESTAMP WITH TIME ZONE", "TIMESTAMP WITHOUT TIME ZONE", "DATE",
]

_PG_TIMESTAMP_ROWS = [
    (base, value, ok)
    for base in _PG_TIMESTAMP_BASES
    for value, ok in (
        (NOW, True), ("2024-01-02", True), ("2024-01-02 03:04:05", True), ("2024-01-02T03:04:05+00:00", True),
        (5, False), (5.5, False), (True, False), (False, False),
        ("abc", False), ("", False), ("not a date", False),
    )
] + [("timestamptz", NOW, True), ("timestamptz", 5, False), ("TIMESTAMP(3)", "2024-01-02", True)]

_PG_CHAR_BASES = ["VARCHAR", "CHARACTER VARYING", "CHAR", "CHARACTER"]

_PG_CHAR_ROWS = [
    (f"{base}(3)", value, ok)
    for base in _PG_CHAR_BASES
    for value, ok in (
        ("abc", True), ("ab", True), ("", True), ("abcd", False), ("abcdefghij", False),
        # other types are not checked
        (12345, True), (1.5, True), (True, True), (NOW, True),
    )
] + [("varchar(3)", "abcd", False), ("VARCHAR(3)", "ábc", True), ("VARCHAR(3)", "ábcd", False),
     ("VARCHAR", "x" * 10000, True), ("CHAR", "x" * 10000, True)]

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


@pytest.mark.parametrize(
    "db_type,value,ok",
    _PG_INT_EDGES + _PG_INT_ROWS + _PG_NUMERIC_ROWS + _PG_BOOLEAN_ROWS + _PG_TIMESTAMP_ROWS
    + _PG_CHAR_ROWS + _PG_UNCHECKED_ROWS + _PG_NONE_ROWS,
)
def test_postgres_value_problem(db_type, value, ok):
    assert (postgres_value_problem(db_type, value) is None) is ok


@pytest.mark.parametrize(
    "db_type,value,reason",
    [
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
    ],
)
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
    )
]

_CQL_DOUBLE_ROWS = [
    ("double", value, ok)
    for value, ok in (
        (5, True), (-2, True), (1.5, True), (10**30, True), (NAN, True), (INF, True),
        (True, False), (False, False),
        ("1.5", False), ("", False),
        (NOW, False), (date(2024, 1, 2), False),
    )
]

_CQL_BOOLEAN_ROWS = [
    ("boolean", value, ok)
    for value, ok in (
        (True, True), (False, True),
        (1, False), (0, False), (1.0, False),
        ("true", False), ("false", False), ("", False),
        (NOW, False),
    )
]

_CQL_TIMESTAMP_ROWS = [
    ("timestamp", value, ok)
    for value, ok in (
        (NOW, True), (date(2024, 1, 2), True), (1704164645000, True), (1.7e12, True), (0, True),
        ("2024-01-02", False), ("", False),
        (True, False), (False, False),
    )
]

_CQL_TEXT_ROWS = [
    ("text", value, True)
    for value in ("abc", "", 5, 2**200, 1.5, NAN, True, False, NOW, date(2024, 1, 2), object())
]

# None is always accepted; types outside the table are not checked
_CQL_OTHER_ROWS = [
    (cql_type, None, True) for cql_type in ("text", "bigint", "double", "boolean", "timestamp")
] + [("uuid", "anything", True), ("int", "anything", True)]

_CQL_UPPER_ROWS = [("BIGINT", 2**63, False), ("Boolean", 1, False), ("DOUBLE", "x", False), ("TIMESTAMP", NOW, True)]


@pytest.mark.parametrize(
    "cql_type,value,ok",
    _CQL_BIGINT_ROWS + _CQL_DOUBLE_ROWS + _CQL_BOOLEAN_ROWS + _CQL_TIMESTAMP_ROWS + _CQL_TEXT_ROWS
    + _CQL_OTHER_ROWS + _CQL_UPPER_ROWS,
)
def test_cassandra_value_problem(cql_type, value, ok):
    assert (cassandra_value_problem(cql_type, value) is None) is ok


@pytest.mark.parametrize(
    "cql_type,value,reason",
    [
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
    ],
)
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
