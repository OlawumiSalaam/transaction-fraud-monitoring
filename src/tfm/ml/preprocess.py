"""Candidate-private preprocessing.

The canonical feature dataset produced (``data/features.py``) is the single
shared substrate for the scorer, the rule engine, and the evidence assembler.
It is **never mutated** by the modelling layer. Every function here
reads a defensive projection of the columns it needs and returns a fresh numeric
matrix; the input DataFrame is left unchanged.

Imputation and scaling are private to a single candidate's pipeline and are fitted
on the training split only, then applied to validation and test (no cross-split
fitting — a temporal-leakage guard, R2).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def extract_matrix(df: pd.DataFrame, columns: list[str]) -> np.ndarray:
    """Project ``columns`` of ``df`` to a float matrix without mutating ``df``.

    Boolean columns become 0.0/1.0; missing values (``None``/``NaN``) are
    preserved as ``NaN`` for the candidate pipeline to handle. The input
    DataFrame is not modified (a fresh array is built column by column).
    """
    frame = df.loc[:, columns]
    cols = [pd.to_numeric(frame[c], errors="coerce").to_numpy(dtype=float) for c in columns]
    return np.column_stack(cols)


def fit_transform(preprocessor: Any | None, matrix: np.ndarray) -> np.ndarray:
    """Fit a preprocessor on ``matrix`` (train) and return the transformed matrix.

    ``None`` means the estimator handles raw values natively (e.g. the NaN-native
    primary); the matrix is returned unchanged.
    """
    if preprocessor is None:
        return matrix
    result: np.ndarray = preprocessor.fit_transform(matrix)
    return result


def transform(preprocessor: Any | None, matrix: np.ndarray) -> np.ndarray:
    """Apply an already-fitted preprocessor to ``matrix`` (val/test/online)."""
    if preprocessor is None:
        return matrix
    result: np.ndarray = preprocessor.transform(matrix)
    return result
