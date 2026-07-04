"""Unit tests for ml/preprocess.py — canonical-immutable extraction (IMP-006)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer

from tfm.ml.preprocess import extract_matrix, fit_transform, transform


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "a": [1.0, 2.0, np.nan],
            "flag": [True, False, True],
            "b": [None, 5.0, 6.0],
        }
    )


def test_extract_matrix_does_not_mutate_input() -> None:
    df = _df()
    before = df.copy(deep=True)
    _ = extract_matrix(df, ["a", "flag", "b"])
    pd.testing.assert_frame_equal(df, before)


def test_extract_matrix_bool_to_float() -> None:
    matrix = extract_matrix(_df(), ["flag"])
    assert matrix.tolist() == [[1.0], [0.0], [1.0]]


def test_extract_matrix_preserves_nan() -> None:
    matrix = extract_matrix(_df(), ["a", "b"])
    assert np.isnan(matrix[2, 0])  # a[2]
    assert np.isnan(matrix[0, 1])  # b[0]


def test_extract_matrix_column_order() -> None:
    matrix = extract_matrix(_df(), ["b", "a"])
    assert matrix[1, 0] == 5.0  # b
    assert matrix[1, 1] == 2.0  # a


def test_fit_transform_none_is_passthrough() -> None:
    matrix = np.array([[1.0, np.nan]])
    out = fit_transform(None, matrix)
    assert out is matrix


def test_fit_transform_imputes() -> None:
    imputer = SimpleImputer(strategy="constant", fill_value=0.0)
    matrix = np.array([[1.0, np.nan], [np.nan, 2.0]])
    out = fit_transform(imputer, matrix)
    assert not np.isnan(out).any()
    assert out.tolist() == [[1.0, 0.0], [0.0, 2.0]]


def test_transform_after_fit() -> None:
    imputer = SimpleImputer(strategy="constant", fill_value=0.0)
    # Fit with observed values in both columns so neither is dropped.
    fit_transform(imputer, np.array([[1.0, 2.0], [3.0, 4.0]]))
    out = transform(imputer, np.array([[np.nan, np.nan]]))
    assert out.tolist() == [[0.0, 0.0]]
