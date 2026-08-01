"""CSV loading and lightweight type inference."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Dict

import pandas as pd

from polyglotimportcsv.casting import is_boolean_series


def read_csv(path: str | Path) -> pd.DataFrame:
    """
    Load CSV as strings first to avoid the C parser mis-splitting fields that contain
    ``+`` (e.g. ``...+0000`` in timestamps) or other special characters.
    """
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


#: Share of values that must parse as dates for a column to count as datetime.
_DATETIME_THRESHOLD = 0.85


#: Distinct values parsed per probe round before the decision bounds are re-checked.
_DATETIME_PROBE_CHUNK = 512


def _parse_datetimes(s: pd.Series) -> pd.Series:
    """Coerce a string column to datetimes, preferring the vectorized ISO path.

    Called with no ``format=``, pandas falls back to per-element ``dateutil``
    parsing — which profiling showed to be ~30x the cost of parsing the CSV itself
    and the single largest item in a large import. ISO-8601 input takes the C path
    instead; only the values it rejects go to ``dateutil``, so the set of values
    that end up parsed is the same as the plain call (dateutil accepts a superset
    of what the ISO parser does).
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        try:
            out = pd.to_datetime(s, errors="coerce", utc=True, format="ISO8601")
        except (ValueError, TypeError):
            return pd.to_datetime(s, errors="coerce", utc=True)
        missing = out.isna()
        if missing.any():
            out[missing] = pd.to_datetime(s[missing], errors="coerce", utc=True)
        return out


def _exceeds_datetime_share(non_empty: pd.Series, threshold: float) -> bool:
    """Does more than ``threshold`` of ``non_empty`` parse as a datetime?

    Answers exactly what ``_parse_datetimes(col).notna().mean() > threshold``
    answers, without parsing what cannot change the verdict. Probing every row was
    the single largest cost of a large import — and almost all of it was spent
    proving that plainly non-date columns (names, e-mails, URLs, order numbers)
    are not dates, one ``dateutil`` call per row.

    Two exact reductions:

    * **De-duplicate.** Parsing is a pure function of the value, so a value that
      occurs 33 times is parsed once and weighted by its count.
    * **Stop once the outcome is settled.** Distinct values are visited
      most-frequent-first; after each round the parsed weight is compared against
      the threshold and the still-achievable weight against it too. A column that
      is not dates is decided as soon as failures pass ``1 - threshold`` of the
      rows, which for real data is a few hundred values rather than every row.
    """
    counts = non_empty.value_counts()
    total = int(counts.to_numpy().sum())
    if total == 0:
        return False
    need = threshold * total
    values, weights = counts.index, counts.to_numpy()
    parsed_weight = failed_weight = 0
    for start in range(0, len(values), _DATETIME_PROBE_CHUNK):
        chunk = values[start : start + _DATETIME_PROBE_CHUNK]
        w = weights[start : start + _DATETIME_PROBE_CHUNK]
        ok = _parse_datetimes(pd.Series(chunk, dtype=object)).notna().to_numpy()
        parsed_weight += int(w[ok].sum())
        failed_weight += int(w[~ok].sum())
        if parsed_weight > need:
            return True  # the rest can only add to it
        if total - failed_weight <= need:
            return False  # even parsing every remaining value cannot reach it
    return parsed_weight > need


def infer_column_kinds(df: pd.DataFrame) -> Dict[str, str]:
    """
    Infer a coarse kind per column: 'empty', 'integer', 'float', 'datetime', 'string'.
    Used for filter validation and coercion hints.
    """
    kinds: Dict[str, str] = {}
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_integer_dtype(s):
            kinds[col] = "integer"
            continue
        if pd.api.types.is_float_dtype(s):
            kinds[col] = "float"
            continue
        if pd.api.types.is_datetime64_any_dtype(s):
            kinds[col] = "datetime"
            continue
        s2 = s.replace("", pd.NA).dropna()
        if s2.empty:
            kinds[col] = "empty"
            continue
        if is_boolean_series(s2):
            kinds[col] = "boolean"
            continue
        # Numeric before datetime: pandas reads a bare 4-digit integer as a year
        # ("1000" -> 1000-01-01), so an ID column running past 999 clears the
        # datetime threshold below and gets cast to timestamps. A fully numeric
        # column is a number; genuinely numeric dates (YYYYMMDD) are ambiguous
        # and must be declared with an explicit db_type in the import config.
        num = pd.to_numeric(s2, errors="coerce")
        if num.notna().all():
            kinds[col] = "integer" if (num % 1 == 0).all() else "float"
            continue
        if _exceeds_datetime_share(s2, _DATETIME_THRESHOLD):
            kinds[col] = "datetime"
            continue
        kinds[col] = "string"
    return kinds
