"""Unit tests for evaluation/model_eval.py (FR-22)."""

from __future__ import annotations

import numpy as np

from evaluation.model_eval import EvalMetrics, compute_metrics


def test_perfect_separation_metrics() -> None:
    y = np.array([0, 0, 1, 1])
    p = np.array([0.1, 0.2, 0.8, 0.9])
    m = compute_metrics(y, p, eval_threshold=0.5)
    assert m.pr_auc == 1.0
    assert m.roc_auc == 1.0
    assert m.precision == 1.0
    assert m.recall == 1.0
    assert m.n == 4
    assert m.n_positive == 2


def test_brier_matches_manual() -> None:
    y = np.array([0, 1])
    p = np.array([0.25, 0.75])
    m = compute_metrics(y, p, eval_threshold=0.5)
    # Brier = mean((p - y)^2) = mean(0.0625, 0.0625) = 0.0625
    assert abs(m.brier - 0.0625) < 1e-9


def test_recall_at_threshold() -> None:
    y = np.array([1, 1, 1, 0])
    p = np.array([0.9, 0.4, 0.6, 0.1])  # at 0.5, positives predicted for idx 0,2
    m = compute_metrics(y, p, eval_threshold=0.5)
    assert abs(m.recall - (2 / 3)) < 1e-9


def test_single_class_gives_nan_aucs() -> None:
    y = np.array([0, 0, 0])
    p = np.array([0.1, 0.2, 0.3])
    m = compute_metrics(y, p, eval_threshold=0.5)
    assert np.isnan(m.pr_auc)
    assert np.isnan(m.roc_auc)


def test_eval_metrics_frozen() -> None:
    m = compute_metrics(np.array([0, 1]), np.array([0.2, 0.8]), 0.5)
    assert isinstance(m, EvalMetrics)
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        m.pr_auc = 0.0  # type: ignore[misc]
