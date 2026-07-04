"""Scorer: calibrated probability plus contributing signals (FR-3).

Contract (Addendum §4 — Scorer):
  In:  a ``FeatureVector`` (the shared substrate from M1).
  Out: ``Score{probability, calibrated, contributing_signals}``.

Architectural responsibility (Layer Separation): the scorer *predicts* — it
produces a calibrated probability and the signals behind it. It does not
recommend, rule, explain, or decide. Those are separate layers.

Invariants:
  - Deterministic given inputs and a pinned model version (NFR-5).
  - Only a leakage-gate-passing model version is loadable in the online path
    (FR-4); this is enforced by the registry (``ml/registry.py``), not here.
  - ``sim_flagged`` is never an input; the ``FeatureVector`` does not carry it.

The contributing signals are derived from the model's global permutation
importances and the training-set association direction of each feature (both
computed once at training time and pinned into the artifact). They are a
deterministic, interpretable "which known features stand out for this
transaction" — not a per-instance attribution method. They are labelled as such
so the evidence assembler (M4) and explanation layer (M6) reference only known,
human-readable values.

Spec references: FR-3, FR-5, Addendum §4.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np
from pydantic import BaseModel, ConfigDict

from tfm.schema.evidence import FeatureVector

SignalDirection = str  # "increases" | "decreases"


class ContributingSignal(BaseModel):
    """One feature standing behind a score, with its value and association.

    ``direction`` is the training-set association of this feature with fraud
    ("increases" or "decreases" the modelled risk), pinned at training time.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    value: float
    direction: SignalDirection


class Score(BaseModel):
    """The scorer's output (Addendum §4)."""

    model_config = ConfigDict(frozen=True)

    probability: float
    calibrated: bool
    contributing_signals: tuple[ContributingSignal, ...]


@runtime_checkable
class Scorer(Protocol):
    """The online scoring interface consumed by the operational path.

    Implemented by ``FittedScorer``. The API layer injects a ``Scorer`` so the
    model version is a pinned, swappable dependency (Implementation Plan §7).
    """

    model_version_id: str

    def score(self, features: FeatureVector) -> Score: ...


def feature_vector_to_row(features: FeatureVector, columns: list[str]) -> list[float]:
    """Project a ``FeatureVector`` onto an ordered numeric row for the model.

    Boolean fields become 0.0/1.0; ``None`` becomes ``NaN`` (the primary model
    handles NaN natively; other candidates impute inside their own pipeline).
    Column names correspond one-to-one to ``FeatureVector`` field names.
    """
    row: list[float] = []
    for name in columns:
        raw = getattr(features, name)
        if raw is None:
            row.append(float("nan"))
        elif isinstance(raw, bool):
            row.append(1.0 if raw else 0.0)
        else:
            row.append(float(raw))
    return row


class FittedScorer:
    """A pinned, fitted, calibrated scorer implementing the ``Scorer`` protocol.

    Holds the calibrated estimator, the ordered feature columns it was trained
    on, an optional fitted preprocessor (``None`` for the NaN-native primary),
    and the pinned contributing-signal metadata. Picklable via the registry.
    """

    def __init__(
        self,
        *,
        model_version_id: str,
        estimator: object,  # a fitted classifier exposing predict_proba
        feature_columns: list[str],
        preprocessor: object | None,
        signal_top_features: list[str],
        signal_directions: dict[str, SignalDirection],
        calibrated: bool,
    ) -> None:
        self.model_version_id = model_version_id
        self._estimator = estimator
        self._feature_columns = feature_columns
        self._preprocessor = preprocessor
        self._signal_top_features = signal_top_features
        self._signal_directions = signal_directions
        self._calibrated = calibrated

    def score(self, features: FeatureVector) -> Score:
        """Produce a calibrated probability and its contributing signals."""
        row = feature_vector_to_row(features, self._feature_columns)
        matrix = np.asarray([row], dtype=float)
        if self._preprocessor is not None:
            matrix = self._preprocessor.transform(matrix)  # type: ignore[attr-defined]

        proba = self._estimator.predict_proba(matrix)  # type: ignore[attr-defined]
        probability = float(proba[0][1])

        signals = tuple(
            ContributingSignal(
                name=name,
                value=float(getattr(features, name)),
                direction=self._signal_directions.get(name, "increases"),
            )
            for name in self._signal_top_features
            if getattr(features, name, None) is not None
        )
        return Score(
            probability=probability,
            calibrated=self._calibrated,
            contributing_signals=signals,
        )
