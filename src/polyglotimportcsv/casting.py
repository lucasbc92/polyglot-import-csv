"""Kind→type table and native-value casting for typed columns."""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

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


def cast_frame(df: pd.DataFrame, kinds: Dict[str, str]) -> pd.DataFrame:
    """Return a copy with typed columns converted to native values.

    Only integer/float/boolean/datetime columns are converted (empty cells
    become None); string columns keep their raw values, including ''.
    """
    out = df.copy()
    for col in out.columns:
        kind = kinds.get(col, "string")
        if kind in ("integer", "float", "boolean", "datetime"):
            # Build the object column directly from a list of already-cast
            # native Python values, rather than via Series.map(). map()
            # lets pandas infer a dtype for the intermediate result (e.g.
            # float64 for a mix of int and None), which silently upcasts
            # ints to floats (1 -> 1.0) before astype(object) ever runs.
            out[col] = pd.Series(
                [cast_value(v, kind) for v in out[col]],
                index=out.index,
                dtype=object,
            )
    return out
