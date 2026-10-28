"""Check one value against the DBMS type a column is declared with.

Both functions are pure and return ``None`` when the DBMS would accept the value,
otherwise a short reason. The value is what a sink would send: ``None``, ``int``,
``float``, ``bool``, ``datetime`` or ``str``. ``None`` is always accepted here (an
empty key has its own rule); types outside the tables below are not checked.
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any, List, Optional, Tuple

import pandas as pd

_PG_INT_BITS = {
    "SMALLINT": 16, "INT2": 16,
    "INTEGER": 32, "INT": 32, "INT4": 32,
    "BIGINT": 64, "INT8": 64,
}
_PG_NUMERIC = frozenset(
    {"NUMERIC", "DECIMAL", "REAL", "FLOAT4", "DOUBLE PRECISION", "FLOAT8", "FLOAT"}
)
_PG_BOOLEAN = frozenset({"BOOLEAN", "BOOL"})
_PG_BOOLEAN_WORDS = frozenset(
    {"t", "true", "y", "yes", "on", "1", "f", "false", "n", "no", "off", "0"}
)
_PG_TIMESTAMP = frozenset(
    {
        "TIMESTAMP", "TIMESTAMPTZ", "TIMESTAMP WITH TIME ZONE",
        "TIMESTAMP WITHOUT TIME ZONE", "DATE",
    }
)
_PG_CHAR = frozenset({"VARCHAR", "CHARACTER VARYING", "CHAR", "CHARACTER"})

_INTEGER_TEXT = re.compile(r"\s*[+-]?\d+\s*", re.ASCII)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _out_of_range(value: int, bits: int, name: str) -> Optional[str]:
    if -(2 ** (bits - 1)) <= value < 2 ** (bits - 1):
        return None
    return f"out of {name} range"


def _split_db_type(db_type: str) -> Tuple[str, List[int]]:
    """``"numeric (14, 2)"`` -> ``("NUMERIC", [14, 2])``."""
    base, _, rest = db_type.upper().partition("(")
    return base.strip(), [int(n) for n in re.findall(r"-?\d+", rest)]


def _pg_integer_problem(name: str, bits: int, value: Any) -> Optional[str]:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    elif isinstance(value, str) and _INTEGER_TEXT.fullmatch(value):
        value = int(value)
    if not _is_int(value):
        return "not an integer"
    return _out_of_range(value, bits, name)


def _pg_numeric_problem(base: str, params: List[int], value: Any) -> Optional[str]:
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return "not a number"
    if not _is_number(value):
        return "not a number"
    if base in ("NUMERIC", "DECIMAL") and params and (isinstance(value, int) or math.isfinite(value)):
        precision, scale = params[0], params[1] if len(params) > 1 else 0
        if abs(round(value, scale)) >= 10 ** (precision - scale):
            return f"out of {base}({precision},{scale}) range"
    return None


def postgres_value_problem(db_type: str, value: Any) -> Optional[str]:
    """Why PostgreSQL would reject ``value`` for a column of ``db_type``, or ``None``."""
    if value is None:
        return None
    base, params = _split_db_type(db_type)
    if base in _PG_INT_BITS:
        return _pg_integer_problem(base, _PG_INT_BITS[base], value)
    if base in _PG_NUMERIC:
        return _pg_numeric_problem(base, params, value)
    if base in _PG_BOOLEAN:
        if isinstance(value, bool) or (
            isinstance(value, str) and value.strip().lower() in _PG_BOOLEAN_WORDS
        ):
            return None
        return "not a boolean"
    if base in _PG_TIMESTAMP:
        if isinstance(value, datetime) or (
            isinstance(value, str) and not pd.isna(pd.to_datetime(value, errors="coerce"))
        ):
            return None
        return "not a date/time"
    if base in _PG_CHAR and params and isinstance(value, str) and len(value) > params[0]:
        return f"longer than {base}({params[0]})"
    return None


def cassandra_value_problem(cql_type: str, value: Any) -> Optional[str]:
    """Why Cassandra would reject ``value`` for a column of ``cql_type``, or ``None``.

    The types are the ones the importer creates: ``text``, ``bigint``, ``double``,
    ``boolean`` and ``timestamp``.
    """
    if value is None:
        return None
    cql_type = cql_type.lower()
    if cql_type == "bigint":
        if not _is_int(value):
            return "not an integer"
        return _out_of_range(value, 64, cql_type)
    if cql_type == "double" and not _is_number(value):
        return "not a number"
    if cql_type == "boolean" and not isinstance(value, bool):
        return "not a boolean"
    if cql_type == "timestamp" and not (isinstance(value, date) or _is_number(value)):
        return "not a date, datetime or number"
    return None
