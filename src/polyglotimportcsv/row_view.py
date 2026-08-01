"""Row-wise reads that do not materialize the whole frame.

``DataFrame.iterrows()`` goes through ``DataFrame.values``, which interleaves
*every* column into one boxed object matrix before yielding anything, then builds
a fresh ``Series`` per row. An entity that maps 3 of 39 columns therefore pays for
all 39, and the up-front matrix is a single allocation proportional to the whole
partition -- at 100k rows that is the allocation that aborted a benchmark matrix
(``Unable to allocate 11.6 MiB for an array with shape (39, 38833)``).

``iter_rows`` reads each column once as a NumPy array and hands out a lightweight
view exposing the same surface the row-shaping helpers already use -- ``row[col]``,
``row.get(col)``, ``col in row.index``, ``list(row.index)`` -- so the importers and
sinks keep their per-row logic unchanged. The column list is built once per frame
instead of once per row.

Values come back as NumPy scalars rather than the Python objects the object-matrix
detour produced. Every consumer funnels them through ``materialize.cell_scalar``
(``.item()``) or ``pd.isna``, both of which treat the two identically; the
equivalence tests in ``tests/test_row_view.py`` pin that down against the real
reference dataset.

Column labels are assumed unique, which the config/mapping layer already
guarantees (the union superset de-dupes by first-seen name).
"""

from __future__ import annotations

from typing import Any, Dict, Iterator

import numpy as np
import pandas as pd


class RowView:
    """Mapping-like view of one row, backed by column arrays shared frame-wide."""

    __slots__ = ("_cols", "_i", "index")

    def __init__(self, cols: Dict[str, np.ndarray], i: int, index: pd.Index) -> None:
        self._cols = cols
        self._i = i
        #: The frame's columns, shared by every row (not rebuilt per row).
        self.index = index

    def __getitem__(self, key: str) -> Any:
        return self._cols[key][self._i]

    def get(self, key: str, default: Any = None) -> Any:
        col = self._cols.get(key)
        return default if col is None else col[self._i]

    def __contains__(self, key: str) -> bool:
        return key in self._cols

    def keys(self):
        return self.index

    def to_dict(self) -> Dict[str, Any]:
        return {name: col[self._i] for name, col in self._cols.items()}


def iter_rows(df: pd.DataFrame) -> Iterator[RowView]:
    """Yield one ``RowView`` per row of ``df``, in order.

    Drop-in for ``for _, row in df.iterrows()`` wherever the body only reads
    cells by label.
    """
    cols = {name: df[name].to_numpy() for name in df.columns}
    index = df.columns
    for i in range(len(df)):
        yield RowView(cols, i, index)
