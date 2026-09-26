"""Per-entity data display for the streaming path (--sample, --show-data, --no-data).

The materialize path dumps each bound entity from a frame it already holds.
The stream path never holds a whole entity, so it watches the batches as they
are written instead: the sample keeps at most N rows per partition, and
--show-data prints each batch as it goes. Either way the memory added is
bounded by N rows or one batch, not by the size of the file.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pandas as pd
from rich.text import Text

from polyglotimportcsv.reporting import (
    DEFAULT_SAMPLE_SIZE,
    dump_rows,
    dump_rows_page,
    print_rich,
)

_Key = Tuple[str, str]


def _label(key: _Key) -> str:
    return f"{key[0]} · {key[1]}"


class StreamDataPreview:
    """Collect what the stream path writes, for the per-entity data display.

    ``show_data`` follows the CLI tri-state: ``None`` samples the first
    ``sample_size`` rows of each partition, ``True`` prints every row, and
    ``False`` prints nothing.
    """

    def __init__(
        self, show_data: Optional[bool] = None, sample_size: int = DEFAULT_SAMPLE_SIZE
    ) -> None:
        self._show_data = show_data
        self._sample_size = sample_size
        self._samples = {}  # type: Dict[_Key, List[pd.DataFrame]]
        self._kept = {}  # type: Dict[_Key, int]
        self._totals = {}  # type: Dict[_Key, int]
        self._printed = {}  # type: Dict[_Key, int]

    def observe(self, dbms: str, partition: str, frame: pd.DataFrame) -> None:
        """Record one batch that ``dbms`` has just written to ``partition``."""
        if self._show_data is False:
            return
        key = (dbms, partition)
        self._totals[key] = self._totals.get(key, 0) + len(frame)
        if self._show_data is True:
            start = self._printed.get(key, 0)
            if start == 0:
                print_rich(Text(f"  {_label(key)}:"))
            dump_rows_page(frame.to_dict(orient="records"), start=start + 1)
            self._printed[key] = start + len(frame)
            return
        room = self._sample_size - self._kept.get(key, 0)
        if room > 0:
            part = frame.head(room).copy()
            self._samples.setdefault(key, []).append(part)
            self._kept[key] = self._kept.get(key, 0) + len(part)

    def finish(self) -> None:
        """Print the sample of every partition written, in first-written order."""
        if self._show_data is not None:
            return
        for key, total in self._totals.items():
            parts = self._samples.get(key) or []
            rows = pd.concat(parts, ignore_index=True).to_dict(orient="records") if parts else []
            dump_rows(_label(key), rows, total=total)
