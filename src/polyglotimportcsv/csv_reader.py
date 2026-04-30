"""CSV loading and lightweight type inference."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd


def read_csv(path: str | Path) -> pd.DataFrame:
    """
    Load CSV as strings first to avoid the C parser mis-splitting fields that contain
    ``+`` (e.g. ``...+0000`` in timestamps) or other special characters.
    """
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


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
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            parsed = pd.to_datetime(s2, errors="coerce", utc=True)
        if parsed.notna().mean() > 0.85:
            kinds[col] = "datetime"
            continue
        num = pd.to_numeric(s2, errors="coerce")
        if num.notna().all():
            kinds[col] = "integer" if (num % 1 == 0).all() else "float"
            continue
        kinds[col] = "string"
    return kinds


def load_csv_with_inference(path: str | Path) -> Tuple[pd.DataFrame, Dict[str, str]]:
    df = read_csv(path)
    kinds = infer_column_kinds(df)
    return df, kinds
