"""Shared fit / predict primitives for the modelling layer.

These low-level helpers are used by both the training orchestration
(``ml/train.py``) and the leakage gate (``evaluation/leakage_gate.py``), so they
live in a dependency-free module to avoid an import cycle between the two.

Every function reads a defensive projection of the canonical dataset and never
mutates it (IMP-006). Preprocessing is fitted on the training matrix only.

Spec references: FR-3, §6.5, R2; IMP-006.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from tfm.ml.candidates import CandidateSpec
from tfm.ml.preprocess import extract_matrix, fit_transform, transform


@dataclass(frozen=True)
class FittedCandidate:
    """A fitted candidate: its spec, fitted preprocessor, and fitted estimator."""

    spec: CandidateSpec
    preprocessor: Any | None
    estimator: Any
    feature_columns: list[str]


def _labels(df: pd.DataFrame, label_col: str) -> np.ndarray:
    labels: np.ndarray = df[label_col].astype(int).to_numpy()
    return labels


def fit_candidate(
    spec: CandidateSpec, train_df: pd.DataFrame, label_col: str = "label"
) -> FittedCandidate:
    """Fit a candidate's preprocessor + estimator on the training split only."""
    features = list(spec.feature_columns)
    x_train = extract_matrix(train_df, features)
    y_train = _labels(train_df, label_col)

    preprocessor = spec.make_preprocessor()
    x_proc = fit_transform(preprocessor, x_train)

    estimator = spec.make_estimator()
    estimator.fit(x_proc, y_train)

    return FittedCandidate(
        spec=spec,
        preprocessor=preprocessor,
        estimator=estimator,
        feature_columns=features,
    )


def predict_proba(fitted: FittedCandidate, df: pd.DataFrame) -> np.ndarray:
    """Return P(fraud) for each row of ``df`` using a fitted candidate."""
    x_raw = extract_matrix(df, fitted.feature_columns)
    x_proc = transform(fitted.preprocessor, x_raw)
    proba: np.ndarray = fitted.estimator.predict_proba(x_proc)[:, 1]
    return proba


def permutation_importance_pr_auc(
    fitted: FittedCandidate,
    df: pd.DataFrame,
    label_col: str,
    n_repeats: int,
    seed: int,
) -> dict[str, float]:
    """Model-agnostic permutation importance measured as PR-AUC (average precision) drop.

    For each feature, its values are shuffled ``n_repeats`` times (raw, before
    the candidate's own preprocessing) and the mean drop in PR-AUC is recorded.
    Deterministic given ``seed``. Never mutates ``df`` (operates on a copy of the
    extracted matrix).
    """
    y = _labels(df, label_col)
    base_score = float(average_precision_score(y, predict_proba(fitted, df)))
    x_raw = extract_matrix(df, fitted.feature_columns)
    rng = np.random.default_rng(seed)

    importances: dict[str, float] = {}
    for j, col in enumerate(fitted.feature_columns):
        drops: list[float] = []
        for _ in range(n_repeats):
            x_shuffled = x_raw.copy()
            rng.shuffle(x_shuffled[:, j])
            x_proc = transform(fitted.preprocessor, x_shuffled)
            proba = fitted.estimator.predict_proba(x_proc)[:, 1]
            drops.append(base_score - float(average_precision_score(y, proba)))
        importances[col] = float(np.mean(drops))
    return importances


def association_directions(
    df: pd.DataFrame, feature_columns: list[str], label_col: str = "label"
) -> dict[str, str]:
    """Sign of each feature's training-set association with the fraud label.

    Returns "increases" if the feature's mean is higher among fraud rows than
    among non-fraud rows, else "decreases". Used to label contributing signals
    (a global, deterministic direction — not a per-instance attribution).
    """
    y = _labels(df, label_col)
    matrix = extract_matrix(df, feature_columns)
    fraud_mask = y == 1
    nonfraud_mask = ~fraud_mask

    directions: dict[str, str] = {}
    for j, col in enumerate(feature_columns):
        column = matrix[:, j]
        fraud_mean = float(np.nanmean(column[fraud_mask])) if fraud_mask.any() else 0.0
        nonfraud_mean = float(np.nanmean(column[nonfraud_mask])) if nonfraud_mask.any() else 0.0
        directions[col] = "increases" if fraud_mean >= nonfraud_mean else "decreases"
    return directions
