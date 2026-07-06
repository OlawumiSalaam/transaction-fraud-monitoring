"""Probability calibration: isotonic / Platt with a small-fold guard.

The scorer must expose a *calibrated* probability so a reported 0.7 means roughly
70% observed fraud. The calibrator is fitted on the validation split only
(never the test split — an out-of-time guard) and applied on top of the base
estimator's raw probability.

Isotonic regression can overfit on small folds; the ``auto``
policy falls back to Platt (sigmoid) scaling when the validation split holds fewer
than a configured number of fraud examples, and otherwise picks whichever of the
two yields the lower validation Brier score.

The reliability/Brier *measurement* lives in ``evaluation/calibration_report.py``;
this module chooses, fits, and applies the calibrator.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

from tfm.config.settings import CalibrationConfig


class Calibrator(Protocol):
    """Maps raw probabilities to calibrated probabilities."""

    def predict(self, raw_prob: np.ndarray) -> np.ndarray: ...


class _IsotonicCalibrator:
    """Isotonic regression calibrator (monotonic, non-parametric)."""

    def __init__(self) -> None:
        self._model = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)

    def fit(self, raw_prob: np.ndarray, y_true: np.ndarray) -> _IsotonicCalibrator:
        self._model.fit(raw_prob, y_true)
        return self

    def predict(self, raw_prob: np.ndarray) -> np.ndarray:
        out: np.ndarray = np.clip(self._model.predict(raw_prob), 0.0, 1.0)
        return out


class _SigmoidCalibrator:
    """Platt (sigmoid) calibrator: a 1-D logistic fit on raw probabilities."""

    def __init__(self) -> None:
        self._model = LogisticRegression()

    def fit(self, raw_prob: np.ndarray, y_true: np.ndarray) -> _SigmoidCalibrator:
        self._model.fit(raw_prob.reshape(-1, 1), y_true)
        return self

    def predict(self, raw_prob: np.ndarray) -> np.ndarray:
        out: np.ndarray = self._model.predict_proba(raw_prob.reshape(-1, 1))[:, 1]
        return out


def choose_and_fit_calibrator(
    raw_val: np.ndarray, y_val: np.ndarray, config: CalibrationConfig
) -> tuple[Calibrator, str]:
    """Choose and fit a calibrator on the validation split.

    Returns the fitted calibrator and the method name ("isotonic" | "sigmoid").
    """
    raw_val = np.asarray(raw_val, dtype=float)
    y_val = np.asarray(y_val).astype(int)
    n_fraud = int(y_val.sum())

    if config.method == "isotonic":
        return _IsotonicCalibrator().fit(raw_val, y_val), "isotonic"
    if config.method == "sigmoid":
        return _SigmoidCalibrator().fit(raw_val, y_val), "sigmoid"

    # auto: guard isotonic against small fraud folds; otherwise pick by Brier.
    if n_fraud < config.min_fraud_for_isotonic:
        return _SigmoidCalibrator().fit(raw_val, y_val), "sigmoid"

    isotonic = _IsotonicCalibrator().fit(raw_val, y_val)
    sigmoid = _SigmoidCalibrator().fit(raw_val, y_val)
    brier_iso = brier_score_loss(y_val, isotonic.predict(raw_val))
    brier_sig = brier_score_loss(y_val, sigmoid.predict(raw_val))
    if brier_iso <= brier_sig:
        return isotonic, "isotonic"
    return sigmoid, "sigmoid"


class CalibratedModel:
    """Wraps a fitted base estimator with a fitted calibrator.

    ``predict_proba`` expects an already-preprocessed matrix (the ``FittedScorer``
    applies the candidate preprocessor first) and returns calibrated two-column
    probabilities. Picklable for the model registry.
    """

    def __init__(self, base_estimator: object, calibrator: Calibrator, method: str) -> None:
        self._base = base_estimator
        self._calibrator = calibrator
        self.method = method

    def predict_proba(self, matrix: np.ndarray) -> np.ndarray:
        raw: np.ndarray = self._base.predict_proba(matrix)[:, 1]  # type: ignore[attr-defined]
        calibrated = self._calibrator.predict(raw)
        return np.column_stack([1.0 - calibrated, calibrated])
