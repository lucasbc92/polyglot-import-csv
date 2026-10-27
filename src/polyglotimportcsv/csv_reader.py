"""CSV loading and lightweight type inference."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

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


def _is_digits_only(s: pd.Series) -> pd.Series:
    """Mask of the values that are nothing but ASCII digits once stripped."""
    return s.astype(str).str.strip().str.fullmatch(r"[0-9]+")


def _datetime_evidence(
    non_empty: pd.Series, threshold: float, early_stop: bool = True
) -> Tuple[int, int]:
    """Count the values of ``non_empty`` known to parse as datetimes and known not to.

    Returns ``(parsed, failed)``: at least ``parsed`` values parse and at most
    ``total - failed`` do, the two meeting when the probe ran to the end. It stops as
    soon as the verdict ``parsed > threshold * total`` is settled, without parsing
    what cannot change it. Probing every row was the single largest cost of a large
    import — and almost all of it was spent proving that plainly non-date columns
    (names, e-mails, URLs, order numbers) are not dates, one ``dateutil`` call per row.
    With ``early_stop=False`` nothing is skipped but the digit-only values: every
    distinct value is probed, so ``parsed + failed == total``.

    Two exact reductions:

    * **De-duplicate.** Parsing is a pure function of the value, so a value that
      occurs 33 times is parsed once and weighted by its count.
    * **Stop once the outcome is settled.** Distinct values are visited
      most-frequent-first; before each round the parsed weight is compared against
      the threshold and the still-achievable weight against it too. A column that
      is not dates is decided as soon as failures pass ``1 - threshold`` of the
      rows, which for real data is a few hundred values rather than every row.

    One rule goes beyond the plain parse: a value that is only ASCII digits counts
    as a failure and is never parsed. pandas reads a bare integer as a year
    ("1000" -> 1000-01-01), so an ID column running past 999 would clear the
    threshold and be cast to timestamps. Genuinely numeric dates (YYYYMMDD) are
    ambiguous and must be declared with an explicit db_type in the import config.
    """
    counts = non_empty.value_counts()
    total = int(counts.to_numpy().sum())
    if total == 0:
        return 0, 0
    need = threshold * total
    values, weights = counts.index, counts.to_numpy()
    digits = _is_digits_only(pd.Series(values)).to_numpy(dtype=bool)
    parsed_weight, failed_weight = 0, int(weights[digits].sum())
    values, weights = values[~digits], weights[~digits]
    for start in range(0, len(values), _DATETIME_PROBE_CHUNK):
        if early_stop:
            if parsed_weight > need:
                break  # the rest can only add to it
            if total - failed_weight <= need:
                break  # even parsing every remaining value cannot reach it
        chunk =values[start : start + _DATETIME_PROBE_CHUNK]
        w = weights[start : start + _DATETIME_PROBE_CHUNK]
        ok = _parse_datetimes(pd.Series(chunk, dtype=object)).notna().to_numpy()
        parsed_weight += int(w[ok].sum())
        failed_weight += int(w[~ok].sum())
    return parsed_weight, failed_weight


def _exceeds_datetime_share(non_empty: pd.Series, threshold: float) -> bool:
    """Does more than ``threshold`` of ``non_empty`` parse as a datetime?"""
    parsed, _ = _datetime_evidence(non_empty, threshold)
    return parsed > threshold * int(non_empty.count())


@dataclass
class ColumnStats:
    """Type evidence for one column, accumulated chunk by chunk.

    Lets a whole file be classified in bounded memory: ``update`` takes the raw
    text of the column in one chunk, ``merged`` combines two accumulators, and
    ``kind`` reads the verdict. The flags are ANDs and the counters are sums.

    ``dates_min`` and ``dates_max`` bracket how many values parse as datetimes: at
    least ``dates_min`` do and at most ``dates_max`` can. By default each chunk stops
    probing once *its own* verdict is settled, so a datetime chunk keeps only a
    lower bound of about ``threshold * n`` and a numeric chunk only an upper bound.
    The bounds of the merged stats can then straddle the threshold even far from
    it, for example one dirty chunk among clean ones.

    So the verdict does not depend on how the file was cut only when every chunk
    settles the same way, or when the stats are exact (``update(..., exact=True)``
    keeps ``dates_min == dates_max``). Otherwise ``decided()`` is False, ``kind()``
    falls back to 'string', and the caller is expected to settle the column with
    exact stats over a re-read of it.
    """

    non_empty: int = 0
    all_boolean: bool = True
    all_numeric: bool = True
    all_integral: bool = True
    dates_min: int = 0
    dates_max: int = 0

    def update(self, values: pd.Series, exact: bool = False) -> None:
        """Fold in the raw text of this column in one chunk; empty cells are ignored.

        ``exact=True`` skips every shortcut: each distinct value is probed (digit-only
        values still count as failures without a parse), numeric chunks included, so
        the chunk adds the same amount to ``dates_min`` and ``dates_max``. It costs a
        parse per distinct value; it is for the columns ``decided()`` left open.
        """
        s2 = values.replace("", pd.NA).dropna()
        n = len(s2)
        if n == 0:
            return
        self.non_empty += n
        self.all_boolean &= is_boolean_series(s2)
        # Numeric before datetime: a fully numeric chunk is a number, so unless exact
        # it is never probed for dates (and a bare digit string is never a date, see
        # ``_datetime_evidence``). It can only add an upper bound: whatever is not
        # digit-only might still parse, should a later chunk make the column text.
        num = pd.to_numeric(s2, errors="coerce")
        numeric_chunk = bool(num.notna().all())
        self.all_numeric &= numeric_chunk
        if numeric_chunk:
            self.all_integral &= bool((num % 1 == 0).all())
        if numeric_chunk and not exact:
            self.dates_max += int((~_is_digits_only(s2)).sum())
        else:
            parsed, failed = _datetime_evidence(
                s2, _DATETIME_THRESHOLD, early_stop=not exact
            )
            self.dates_min += parsed
            self.dates_max += n - failed

    def merged(self, other: "ColumnStats") -> "ColumnStats":
        return ColumnStats(
            non_empty=self.non_empty + other.non_empty,
            all_boolean=self.all_boolean and other.all_boolean,
            all_numeric=self.all_numeric and other.all_numeric,
            all_integral=self.all_integral and other.all_integral,
            dates_min=self.dates_min + other.dates_min,
            dates_max=self.dates_max + other.dates_max,
        )

    def decided(self) -> bool:
        """Does the evidence settle ``kind()``, with no fallback?

        False only for a text column whose ``dates_min`` is at or below the threshold
        share and ``dates_max`` above it: the merged bounds straddle the threshold, which
        chunks that stopped probing at their own verdict can do whatever the true
        share is. ``update(..., exact=True)`` over the column resolves it.
        """
        need = _DATETIME_THRESHOLD * self.non_empty
        return (
            self.non_empty == 0
            or self.all_boolean
            or self.all_numeric
            or self.dates_min > need
            or self.dates_max <= need
        )

    def kind(self) -> str:
        """'empty', 'boolean', 'integer', 'float', 'datetime' or 'string'.

        One case is not settled by the evidence (``decided()`` is False): the bounds
        straddle the threshold. It reads as 'string', the kind that casts nothing,
        where a wrong 'datetime' would rewrite the values. That is a provisional
        answer: a caller that needs the true kind resolves the column with exact stats.
        """
        if self.non_empty == 0:
            return "empty"
        if self.all_boolean:
            return "boolean"
        if self.all_numeric:
            return "integer" if self.all_integral else "float"
        need = _DATETIME_THRESHOLD * self.non_empty
        if self.dates_min > need:
            return "datetime"
        if self.dates_max <= need:
            return "string"
        return "string"  # undecided, see above


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
        stats = ColumnStats()
        stats.update(s)
        kinds[col] = stats.kind()
    return kinds
