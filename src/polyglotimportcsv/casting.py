"""Kind→type table and native-value casting for typed columns."""

from __future__ import annotations

import logging
from typing import Any, Dict

import pandas as pd

logger = logging.getLogger(__name__)

#: Inferred column kind -> DDL type used when auto-mapping (spec §2.5).
KIND_TO_DB_TYPE: Dict[str, str] = {
    "integer": "BIGINT",
    "float": "NUMERIC",
    "datetime": "TIMESTAMPTZ",
    "boolean": "BOOLEAN",
    "string": "TEXT",
    "empty": "TEXT",
}

_BOOL_WORDS = {"true", "false"}


def is_boolean_series(non_empty: pd.Series) -> bool:
    """True when every non-empty value is 'true'/'false' (case-insensitive)."""
    vals = {str(v).strip().lower() for v in non_empty}
    return bool(vals) and vals <= _BOOL_WORDS


def cast_value(val: Any, kind: str) -> Any:
    """Convert one CSV string to a native Python value; '' and None become None.

    Caveat: the "boolean" branch assumes ``val`` was already validated by
    ``is_boolean_series`` (i.e. every non-empty value in the column is
    'true'/'false', case-insensitive). It does not itself validate the
    input — any value that isn't the literal string 'true' (case-insensitive)
    silently maps to False, so passing unvalidated/dirty data here can
    produce misleading results.
    """
    if val is None or val == "":
        return None
    if kind == "integer":
        try:
            return int(val)
        except (TypeError, ValueError):
            return val
    if kind == "float":
        try:
            return float(val)
        except (TypeError, ValueError):
            return val
    if kind == "boolean":
        return str(val).strip().lower() == "true"
    if kind == "datetime":
        ts = pd.to_datetime(val, errors="coerce", utc=True)
        return None if pd.isna(ts) else ts.to_pydatetime()
    return val


def _cast_column_vectorized(series: pd.Series, kind: str) -> "tuple[pd.Series, int]":
    """Vectorized cast of one column to native values; return (result, fallbacks).

    Empty cells ('' and None) become None in every kind (masked before the
    converter runs, so NaT/NaN/eq('true') never leak through). For integer
    and float, values the converter can't parse are returned unchanged as
    their original text and counted as fallbacks, matching cast_value's
    try/except contract. For datetime, cast_value has no such fallback (an
    unparseable value always becomes None, never text); this mirrors that
    exactly, though it still counts and warns on the fallback since the
    vectorized path can detect it precisely.
    """
    empty = series.isna() | (series == "")
    original = series.astype(object)
    fallbacks = 0

    if kind == "boolean":
        parsed = series.astype(str).str.strip().str.lower().eq("true")
        out = parsed.astype(object).where(~empty, None)
        return pd.Series(list(out), index=series.index, dtype=object), 0

    if kind in ("integer", "float"):
        num = pd.to_numeric(series.where(~empty), errors="coerce")
        bad = num.isna() & ~empty
        fallbacks = int(bad.sum())
        if kind == "integer":
            vals = [
                None if e else (o if b else int(v))
                for e, b, v, o in zip(empty, bad, num, original)
            ]
        else:
            vals = [
                None if e else (o if b else float(v))
                for e, b, v, o in zip(empty, bad, num, original)
            ]
        return pd.Series(vals, index=series.index, dtype=object), fallbacks

    if kind == "datetime":
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            # format="mixed" is REQUIRED for equivalence with the per-cell path.
            # Without it pandas infers ONE format from the first element and
            # coerces every value in another format to NaT: a column holding
            # "2023-11-02 03:30:00Z" and "2024-01-01T00:00:00Z" (space vs T)
            # loses the second format entirely, while per-cell to_datetime
            # parses both. Verified against pandas in this environment.
            ts = pd.to_datetime(series.where(~empty), errors="coerce",
                                utc=True, format="mixed")
        bad = ts.isna() & ~empty
        fallbacks = int(bad.sum())
        py = ts.dt.to_pydatetime()
        # Unlike integer/float, cast_value's datetime branch has no
        # try/except fallback: an unparseable value always becomes None,
        # never the original text (see cast_value above). Match that exactly
        # so strategy="naive" and strategy="optimized" stay equivalent; we
        # still count and warn on the fallback since we can detect it here.
        vals = [None if (e or b) else d for e, b, d in zip(empty, bad, py)]
        return pd.Series(vals, index=series.index, dtype=object), fallbacks

    return original, 0


def cast_frame(df: pd.DataFrame, kinds: Dict[str, str], *, strategy: str = "optimized") -> pd.DataFrame:
    """Return a copy with typed columns converted to native values.

    ``strategy='naive'`` casts cell by cell (the original path);
    ``strategy='optimized'`` casts per column with pandas. Both yield identical
    values and element types. Only integer/float/boolean/datetime columns are
    converted (empty cells become None); string columns keep raw values.
    """
    out = df.copy()
    for col in out.columns:
        kind = kinds.get(col, "string")
        if kind not in ("integer", "float", "boolean", "datetime"):
            continue
        if strategy == "optimized":
            result, fallbacks = _cast_column_vectorized(out[col], kind)
            out[col] = result
        else:
            values = [cast_value(v, kind) for v in out[col]]
            fallbacks = sum(
                1
                for orig, v in zip(out[col], values)
                if v is orig and orig is not None and orig != ""
            )
            out[col] = pd.Series(values, index=out.index, dtype=object)
        if fallbacks:
            # Datetime failures become None (cast_value has no text fallback
            # for datetime, see above); integer/float failures stay as text.
            outcome = "became None" if kind == "datetime" else "stayed text"
            logger.warning(
                "column %r: %d value(s) could not be cast to %s and %s",
                col, fallbacks, kind, outcome,
            )
        logger.debug("column %r cast to %s (%d value(s))", col, kind, len(out[col]))
    return out
