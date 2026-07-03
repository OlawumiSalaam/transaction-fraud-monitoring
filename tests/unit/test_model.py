"""Unit tests for ml/model.py — Score, Scorer, FittedScorer (FR-3, Addendum §4)."""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError
from sklearn.ensemble import HistGradientBoostingClassifier

from tfm.data.features import FEATURE_COLUMNS
from tfm.ml.model import (
    ContributingSignal,
    FittedScorer,
    Score,
    Scorer,
    feature_vector_to_row,
)
from tfm.schema.evidence import FeatureVector


def _feature_vector(amount: float = 500.0) -> FeatureVector:
    return FeatureVector(
        txn_id="t1",
        account_id="C1",
        counterparty_id="X1",
        amount=amount,
        type_payment=False,
        type_transfer=True,
        type_cash_out=False,
        type_cash_in=False,
        type_debit=False,
        bal_orig_before=1000.0,
        bal_orig_after=200.0,
        bal_dest_before=None,
        bal_dest_after=None,
        frac_bal_orig_moved=0.8,
        orig_account_emptied=False,
        txn_count_24h=4,
        amount_sum_24h=1200.0,
        is_new_counterparty=True,
        distinct_counterparties_seen=2,
    )


def _fitted_histgb() -> HistGradientBoostingClassifier:
    rng = np.random.default_rng(0)
    x = rng.normal(size=(200, len(FEATURE_COLUMNS)))
    y = (x[:, 0] + rng.normal(scale=0.1, size=200) > 0).astype(int)
    model = HistGradientBoostingClassifier(random_state=0)
    model.fit(x, y)
    return model


def _scorer() -> FittedScorer:
    return FittedScorer(
        model_version_id="test-v1",
        estimator=_fitted_histgb(),
        feature_columns=list(FEATURE_COLUMNS),
        preprocessor=None,
        signal_top_features=["amount", "txn_count_24h"],
        signal_directions={"amount": "increases", "txn_count_24h": "increases"},
        calibrated=True,
    )


def test_feature_vector_to_row_order_and_types() -> None:
    fv = _feature_vector()
    row = feature_vector_to_row(fv, ["amount", "type_transfer", "is_new_counterparty"])
    assert row == [500.0, 1.0, 1.0]


def test_feature_vector_to_row_none_becomes_nan() -> None:
    fv = _feature_vector()
    row = feature_vector_to_row(fv, ["bal_dest_before"])
    assert np.isnan(row[0])


def test_score_returns_valid_probability() -> None:
    score = _scorer().score(_feature_vector())
    assert isinstance(score, Score)
    assert 0.0 <= score.probability <= 1.0
    assert score.calibrated is True


def test_score_is_deterministic() -> None:
    scorer = _scorer()
    fv = _feature_vector()
    assert scorer.score(fv).probability == scorer.score(fv).probability


def test_contributing_signals_reference_known_features() -> None:
    score = _scorer().score(_feature_vector())
    names = {s.name for s in score.contributing_signals}
    assert names == {"amount", "txn_count_24h"}
    for signal in score.contributing_signals:
        assert signal.direction in ("increases", "decreases")


def test_contributing_signal_value_matches_feature() -> None:
    score = _scorer().score(_feature_vector(amount=777.0))
    amount_signal = next(s for s in score.contributing_signals if s.name == "amount")
    assert amount_signal.value == 777.0


def test_fitted_scorer_satisfies_scorer_protocol() -> None:
    assert isinstance(_scorer(), Scorer)


def test_score_and_signal_are_frozen() -> None:
    signal = ContributingSignal(name="amount", value=1.0, direction="increases")
    with pytest.raises(ValidationError):
        signal.value = 2.0  # type: ignore[misc]
