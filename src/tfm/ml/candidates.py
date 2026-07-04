"""The bounded candidate model set (FR-3, DF-1).

Three candidates, ratified in Addendum §4 and Implementation Plan §7:

- **HistGradientBoosting** — the interpretable *primary*. Handles ``NaN``
  natively (no imputation of the structural merchant-destination gaps), and its
  behaviour is inspectable via permutation importance. Trained on
  ``PRIMARY_FEATURE_COLUMNS`` — the behavioural substrate, i.e. the canonical
  features minus the quarantined balance artifacts (IMP-011).
- **LightGBM** — the *kitchen-sink comparator*. Trained on
  ``COMPARATOR_FEATURE_COLUMNS`` (the full canonical set + destination-balance
  features), which supplies the DF-1 interpretable-vs-kitchen-sink contrast.
- **Logistic regression** — the *baseline floor*. Imputed and standardised;
  trained on the same behavioural substrate as the primary; sanity-checks that
  the boosters earn their complexity (DF-1).

Each candidate owns its preprocessing (IMP-006). Model hyperparameters are fixed
engineering defaults with a pinned seed for reproducibility (NFR-5); the
governance-sensitive parameters (thresholds, the leakage-gate defaults) live in
versioned config, not here.

Spec references: FR-3, FR-5, DF-1, §6.5; Addendum §4; Implementation Plan §7.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CandidateSpec:
    """A model candidate: its feature set, estimator kind, and preprocessing."""

    name: str
    kind: str  # "histgb" | "lightgbm" | "logistic"
    feature_columns: tuple[str, ...]
    seed: int
    is_primary: bool = False

    def make_preprocessor(self) -> Any | None:
        """Build a fresh, unfitted preprocessor (candidate-private, IMP-006)."""
        from sklearn.impute import SimpleImputer
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        if self.kind == "histgb":
            return None  # NaN-native; no imputation or scaling
        if self.kind == "lightgbm":
            # Zero-impute the augmented destination-balance gaps (IMP-004/IMP-006).
            return SimpleImputer(strategy="constant", fill_value=0.0)
        if self.kind == "logistic":
            return Pipeline(
                steps=[
                    ("impute", SimpleImputer(strategy="constant", fill_value=0.0)),
                    ("scale", StandardScaler()),
                ]
            )
        raise ValueError(f"unknown candidate kind: {self.kind}")

    def make_estimator(self) -> Any:
        """Build a fresh, unfitted estimator with the pinned seed."""
        if self.kind == "histgb":
            from sklearn.ensemble import HistGradientBoostingClassifier

            return HistGradientBoostingClassifier(class_weight="balanced", random_state=self.seed)
        if self.kind == "lightgbm":
            from lightgbm import LGBMClassifier

            return LGBMClassifier(is_unbalance=True, random_state=self.seed, n_jobs=1, verbose=-1)
        if self.kind == "logistic":
            from sklearn.linear_model import LogisticRegression

            return LogisticRegression(
                class_weight="balanced", max_iter=1000, random_state=self.seed
            )
        raise ValueError(f"unknown candidate kind: {self.kind}")


def build_candidates(
    primary_features: list[str],
    comparator_features: list[str],
    seed: int,
) -> list[CandidateSpec]:
    """Assemble the bounded candidate set (primary first).

    ``primary_features`` is ``PRIMARY_FEATURE_COLUMNS`` — the behavioural substrate
    the interpretable primary and the logistic floor train on (the shared canonical
    features minus the quarantined balance artifacts, IMP-011). ``comparator_features``
    is ``COMPARATOR_FEATURE_COLUMNS`` — the full canonical set plus the augmented
    destination-balance signals, used by the kitchen-sink comparator for the DF-1
    contrast.
    """
    return [
        CandidateSpec(
            name="histgb_interpretable",
            kind="histgb",
            feature_columns=tuple(primary_features),
            seed=seed,
            is_primary=True,
        ),
        CandidateSpec(
            name="lightgbm_kitchen_sink",
            kind="lightgbm",
            feature_columns=tuple(comparator_features),
            seed=seed,
        ),
        CandidateSpec(
            name="logistic_floor",
            kind="logistic",
            feature_columns=tuple(primary_features),
            seed=seed,
        ),
    ]
