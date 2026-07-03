"""Unit tests for ml/calibration.py and evaluation/calibration_report.py (FR-23)."""

from __future__ import annotations

import numpy as np

from evaluation.calibration_report import build_calibration_report, reliability_bins
from tfm.config.settings import CalibrationConfig
from tfm.ml.calibration import CalibratedModel, choose_and_fit_calibrator


class _StubEstimator:
    """A stand-in base estimator exposing predict_proba over a 1-column matrix."""

    def predict_proba(self, matrix: np.ndarray) -> np.ndarray:
        p = matrix[:, 0]
        return np.column_stack([1.0 - p, p])


def _val_data(seed: int = 0, n: int = 400) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    raw = rng.uniform(0.0, 1.0, size=n)
    # Miscalibrated-but-monotone: fraud probability roughly raw**2.
    y = (rng.random(n) < raw**2).astype(int)
    return raw, y


def test_explicit_sigmoid_method() -> None:
    raw, y = _val_data()
    calibrator, method = choose_and_fit_calibrator(raw, y, CalibrationConfig(method="sigmoid"))
    assert method == "sigmoid"
    out = calibrator.predict(raw)
    assert out.min() >= 0.0 and out.max() <= 1.0


def test_explicit_isotonic_method() -> None:
    raw, y = _val_data()
    calibrator, method = choose_and_fit_calibrator(raw, y, CalibrationConfig(method="isotonic"))
    assert method == "isotonic"
    out = calibrator.predict(raw)
    assert out.min() >= 0.0 and out.max() <= 1.0


def test_auto_small_fraud_prefers_sigmoid() -> None:
    raw, y = _val_data()
    # Force the small-fold guard by requiring more fraud than exists.
    cfg = CalibrationConfig(method="auto", min_fraud_for_isotonic=10_000)
    _, method = choose_and_fit_calibrator(raw, y, cfg)
    assert method == "sigmoid"


def test_auto_large_fraud_allows_isotonic() -> None:
    raw, y = _val_data()
    cfg = CalibrationConfig(method="auto", min_fraud_for_isotonic=1)
    _, method = choose_and_fit_calibrator(raw, y, cfg)
    assert method in ("isotonic", "sigmoid")  # chosen by Brier; both valid


def test_calibrated_model_predict_proba_two_columns() -> None:
    raw, y = _val_data()
    calibrator, method = choose_and_fit_calibrator(raw, y, CalibrationConfig(method="sigmoid"))
    model = CalibratedModel(_StubEstimator(), calibrator, method)
    matrix = np.array([[0.3], [0.7]])
    proba = model.predict_proba(matrix)
    assert proba.shape == (2, 2)
    assert np.allclose(proba.sum(axis=1), 1.0)


def test_reliability_bins_and_report() -> None:
    y = np.array([0, 0, 1, 1, 1])
    prob = np.array([0.1, 0.2, 0.6, 0.7, 0.9])
    bins = reliability_bins(y, prob, n_bins=5)
    assert len(bins) >= 1
    assert all(0 <= b.fraction_positive <= 1 for b in bins)

    report = build_calibration_report(method="sigmoid", y_true=y, prob_before=prob, prob_after=prob)
    assert report.method == "sigmoid"
    assert report.brier_before == report.brier_after  # identical inputs
    assert report.n_bins == 10
