"""Resolve csv_columns selections (names, 1-based indices, ranges) to header names."""

from __future__ import annotations

import re
from typing import List, Sequence

from polyglotimportcsv.business_exception import MappingError

_RANGE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")
_INDEX = re.compile(r"^\s*(\d+)\s*$")


def select_columns(
    tokens: Sequence, header: Sequence[str], *, context: str = ""
) -> List[str]:
    """Resolve tokens against `header` (data columns only; index 1 = first).

    Returns the selected column names in header order, without duplicates.
    Raises MappingError for out-of-bounds indices/ranges or unknown names.
    """
    header = list(header)
    where = f" in {context}" if context else ""
    chosen: set[int] = set()
    for token in tokens:
        t = str(token)
        m = _RANGE.match(t)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if lo < 1 or hi > len(header) or lo > hi:
                raise MappingError(
                    f"csv_columns range '{t}'{where} out of bounds (valid: 1-{len(header)})."
                )
            chosen.update(range(lo - 1, hi))
            continue
        m = _INDEX.match(t)
        if m:
            i = int(m.group(1))
            if i < 1 or i > len(header):
                raise MappingError(
                    f"csv_columns index '{t}'{where} out of bounds (valid: 1-{len(header)})."
                )
            chosen.add(i - 1)
            continue
        if t not in header:
            raise MappingError(
                f"csv_columns name '{t}'{where} not found in the source header."
            )
        chosen.add(header.index(t))
    return [header[i] for i in sorted(chosen)]
