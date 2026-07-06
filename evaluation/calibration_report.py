"""Calibration reporting: reliability diagram data and Brier score.

Probability calibration in the reliability sense: does a predicted probability of
0.7 correspond to ~70% observed fraud? This module computes the reliability-bin
summary and Brier scores that quantify it. The *choice and fitting* of the
calibrator (isotonic vs Platt, with the small-fold guard) lives in
``ml/calibration.py``; this module only measures.
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, ConfigDict
from sklearn.metrics import brier_score_loss


class ReliabilityBin(BaseModel):
    """One bin of the reliability diagram."""

    model_config = ConfigDict(frozen=True)

    bin_lower: float
    bin_upper: float
    mean_predicted: float
    fraction_positive: float
    count: int


class CalibrationReport(BaseModel):
    """Reliability-bin summary plus Brier scores before and after calibration."""

    model_config = ConfigDict(frozen=True)

    method: str
    brier_before: float
    brier_after: float
    n_bins: int
    bins: tuple[ReliabilityBin, ...]


def reliability_bins(
    y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10
) -> tuple[ReliabilityBin, ...]:
    """Bin predictions into ``n_bins`` equal-width probability bins.

    Empty bins are omitted. Never mutates its inputs.
    """
    y_true = np.asarray(y_true).astype(int)
    y_prob = np.asarray(y_prob, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)

    bins: list[ReliabilityBin] = []
    for i in range(n_bins):
        lo, hi = float(edges[i]), float(edges[i + 1])
        # Last bin is closed on the right to include probability == 1.0.
        if i == n_bins - 1:
            mask = (y_prob >= lo) & (y_prob <= hi)
        else:
            mask = (y_prob >= lo) & (y_prob < hi)
        count = int(mask.sum())
        if count == 0:
            continue
        bins.append(
            ReliabilityBin(
                bin_lower=lo,
                bin_upper=hi,
                mean_predicted=float(y_prob[mask].mean()),
                fraction_positive=float(y_true[mask].mean()),
                count=count,
            )
        )
    return tuple(bins)


def build_calibration_report(
    *,
    method: str,
    y_true: np.ndarray,
    prob_before: np.ndarray,
    prob_after: np.ndarray,
    n_bins: int = 10,
) -> CalibrationReport:
    """Assemble the calibration report from pre- and post-calibration probabilities."""
    y_true = np.asarray(y_true).astype(int)
    return CalibrationReport(
        method=method,
        brier_before=float(brier_score_loss(y_true, prob_before)),
        brier_after=float(brier_score_loss(y_true, prob_after)),
        n_bins=n_bins,
        bins=reliability_bins(y_true, prob_after, n_bins),
    )
