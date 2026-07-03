"""Model evaluation metrics on the out-of-time split (FR-22).

Primaries: PR-AUC (average precision), precision, recall. Secondary: ROC-AUC.
Calibration quality: Brier score. All metrics are computed on the OOT split and
are reported labelled *measured on synthetic PaySim data* (§7, §8).

Precision and recall require an operating threshold; here they are reported at a
configurable evaluation threshold (``eval_threshold`` in ``config/model.yaml``)
purely so the two metrics are defined. The *operating* threshold — the score
bands mapped to clear/hold/escalate — is a governance decision made in M5
(FR-9), not here. PR-AUC and ROC-AUC are threshold-free.

Spec references: FR-22, §8.
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, ConfigDict
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)


class EvalMetrics(BaseModel):
    """Out-of-time evaluation metrics for one model (FR-22)."""

    model_config = ConfigDict(frozen=True)

    pr_auc: float  # average precision (primary)
    precision: float  # at eval_threshold
    recall: float  # at eval_threshold
    roc_auc: float  # secondary
    brier: float  # calibration quality
    eval_threshold: float
    n: int
    n_positive: int


def _safe(metric: float | None) -> float:
    return float("nan") if metric is None else float(metric)


def compute_metrics(y_true: np.ndarray, y_prob: np.ndarray, eval_threshold: float) -> EvalMetrics:
    """Compute the FR-22 metric set from labels and predicted probabilities.

    ROC-AUC and PR-AUC are undefined when only one class is present; they are
    reported as NaN in that degenerate case rather than raising.
    """
    y_true = np.asarray(y_true).astype(int)
    y_prob = np.asarray(y_prob, dtype=float)
    y_pred = (y_prob >= eval_threshold).astype(int)

    n = int(y_true.shape[0])
    n_positive = int(y_true.sum())
    both_classes = 0 < n_positive < n

    pr_auc = _safe(average_precision_score(y_true, y_prob)) if both_classes else float("nan")
    roc_auc = _safe(roc_auc_score(y_true, y_prob)) if both_classes else float("nan")

    return EvalMetrics(
        pr_auc=pr_auc,
        precision=_safe(precision_score(y_true, y_pred, zero_division=0)),
        recall=_safe(recall_score(y_true, y_pred, zero_division=0)),
        roc_auc=roc_auc,
        brier=_safe(brier_score_loss(y_true, y_prob)) if n > 0 else float("nan"),
        eval_threshold=float(eval_threshold),
        n=n,
        n_positive=n_positive,
    )
