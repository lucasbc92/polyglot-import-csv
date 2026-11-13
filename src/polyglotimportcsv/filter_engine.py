"""Apply row filters from configuration to a DataFrame."""

from __future__ import annotations

import operator
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from polyglotimportcsv.business_exception import BusinessException
from polyglotimportcsv.casting import parse_datetimes

#: Placeholder of an ``each`` filter's ``target_suffix`` template.
VALUE_MARKER = "{value}"


def _slugify(value: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value)).strip("_")
    return s or "value"


#: Kinds whose filter values are compared as numbers or instants, not as text.
_TYPED_KINDS = ("integer", "float", "datetime")

_COMPARE = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
}


def _coerce_compare(series: pd.Series, value: Any, kind: str) -> Any:
    """``(column, value)`` as what the column's kind compares: numbers, instants or text.

    ``value`` may be a list (``in``/``not_in``). Instants are parsed with
    ``casting.parse_datetimes``, so a filter keeps the rows the cast would convert.
    """
    if kind in ("integer", "float"):
        return pd.to_numeric(series, errors="coerce"), pd.to_numeric(value, errors="coerce")
    if kind == "datetime":
        return parse_datetimes(series), pd.to_datetime(
            value, errors="coerce", utc=True, format="mixed"
        )
    if isinstance(value, list):
        return series, [str(v) for v in value]
    return series.astype(str), str(value)


def apply_filters(
    df: pd.DataFrame,
    filters: List[Dict[str, Any]],
    column_kinds: Dict[str, str],
) -> pd.DataFrame:
    """Apply all non-`each` filters in order."""
    out = df
    for flt in filters or []:
        if flt.get("operator") == "each":
            continue
        out = _apply_one(out, flt, column_kinds)
    return out


def _apply_one(df: pd.DataFrame, flt: Dict[str, Any], column_kinds: Dict[str, str]) -> pd.DataFrame:
    col = flt["column"]
    op = flt["operator"]
    val = flt.get("value")
    if col not in df.columns:
        raise BusinessException(f"Filter references unknown column: {col}")
    kind = column_kinds.get(col, "string")
    s = df[col].replace("", pd.NA)

    if op in ("in", "not_in"):
        if not isinstance(val, list):
            raise BusinessException(f"Filter '{op}' for {col} requires a list value")
    elif op not in _COMPARE:
        raise BusinessException(f"Unsupported filter operator in apply_filters: {op}")

    left, right = _coerce_compare(s, val, kind)
    # A value that is not of the column's kind compares as NaN: it would silently keep
    # no row, or every row.
    if kind in _TYPED_KINDS and np.any(pd.isna(right)):
        raise BusinessException(f"Filter {op} value is not comparable for column {col}")
    if op == "in":
        mask = left.isin(right)
    elif op == "not_in":
        mask = ~left.isin(right)
    else:
        mask = _COMPARE[op](left, right)
    return df.loc[mask]


def expand_each(
    df: pd.DataFrame,
    filters: List[Dict[str, Any]],
    base_entity_name: str,
) -> List[Tuple[str, pd.DataFrame]]:
    """
    `df` must already have non-`each` filters applied.
    If an `each` filter exists in `filters`, split `df` by that column's distinct values.
    """
    each_filters = [f for f in (filters or []) if f.get("operator") == "each"]
    if not each_filters:
        return [(base_entity_name, df)]
    if len(each_filters) > 1:
        raise BusinessException("Only one 'each' filter per entity is supported in this version.")
    flt = each_filters[0]
    col = flt["column"]
    if col not in df.columns:
        raise BusinessException(f"each filter references unknown column: {col}")
    parts: List[Tuple[str, pd.DataFrame]] = []
    for val, group in df.groupby(df[col].replace("", pd.NA)):
        parts.append((_partition_name(base_entity_name, flt, _slugify(val)), group))
    return parts


def _partition_name(base_entity_name: str, flt: Dict[str, Any], slug: str) -> str:
    """``<entity>_<suffix>``: the ``target_suffix`` template with ``{value}`` replaced
    by ``slug``, or ``slug`` itself when the filter has no template."""
    template = flt.get("target_suffix") or VALUE_MARKER
    return f"{base_entity_name}_{template.replace(VALUE_MARKER, slug)}"


def each_partition_pattern(
    base_entity_name: str, filters: Optional[List[Dict[str, Any]]]
) -> Optional["re.Pattern[str]"]:
    """A pattern whose ``fullmatch`` accepts exactly the names ``expand_each`` can give
    the parts of ``base_entity_name``, or ``None`` when ``filters`` has no ``each``."""
    each_filters = [f for f in (filters or []) if f.get("operator") == "each"]
    if not each_filters:
        return None
    marker = "\0"
    name = re.escape(_partition_name(base_entity_name, each_filters[0], marker))
    return re.compile(name.replace(re.escape(marker), "[A-Za-z0-9_]+"))
