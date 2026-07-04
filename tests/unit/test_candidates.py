"""Unit tests for ml/candidates.py — the bounded candidate set (FR-3, DF-1)."""

from __future__ import annotations

from tfm.data.features import FEATURE_COLUMNS
from tfm.ml.candidates import build_candidates

_AUG = ["bal_dest_before", "bal_dest_after"]


def test_three_candidates_primary_first() -> None:
    cands = build_candidates(FEATURE_COLUMNS, _AUG, seed=42)
    assert len(cands) == 3
    assert cands[0].is_primary is True
    assert sum(c.is_primary for c in cands) == 1


def test_primary_is_interpretable_histgb() -> None:
    primary = build_candidates(FEATURE_COLUMNS, _AUG, seed=42)[0]
    assert primary.kind == "histgb"
    assert tuple(primary.feature_columns) == tuple(FEATURE_COLUMNS)


def test_kitchen_sink_has_augmented_features() -> None:
    cands = build_candidates(FEATURE_COLUMNS, _AUG, seed=42)
    kitchen = next(c for c in cands if c.kind == "lightgbm")
    for feat in _AUG:
        assert feat in kitchen.feature_columns
    # augmented features never enter the interpretable primary
    primary = cands[0]
    for feat in _AUG:
        assert feat not in primary.feature_columns


def test_histgb_has_no_preprocessor() -> None:
    primary = build_candidates(FEATURE_COLUMNS, _AUG, seed=42)[0]
    assert primary.make_preprocessor() is None


def test_logistic_has_pipeline_preprocessor() -> None:
    cands = build_candidates(FEATURE_COLUMNS, _AUG, seed=42)
    logistic = next(c for c in cands if c.kind == "logistic")
    pre = logistic.make_preprocessor()
    assert pre is not None
    assert hasattr(pre, "fit_transform")


def test_estimators_are_fresh_instances() -> None:
    primary = build_candidates(FEATURE_COLUMNS, _AUG, seed=42)[0]
    e1 = primary.make_estimator()
    e2 = primary.make_estimator()
    assert e1 is not e2


def test_seed_is_pinned() -> None:
    primary = build_candidates(FEATURE_COLUMNS, _AUG, seed=7)[0]
    assert primary.seed == 7
    est = primary.make_estimator()
    assert est.random_state == 7
