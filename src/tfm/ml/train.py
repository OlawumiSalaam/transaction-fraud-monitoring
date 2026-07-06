"""Bounded candidate comparison on the out-of-time split.

The training orchestration. Given the canonical feature dataset it:

1. Splits out-of-time (train / val / test) via the configured boundaries.
2. Fits each bounded candidate (primary HistGB, kitchen-sink LightGBM, logistic
   floor), each with its own private preprocessing.
3. Calibrates each on the validation split and evaluates on the OOT test split.
4. Runs the simulator-leakage gate for the two candidates (interpretable
   primary and kitchen-sink comparator) — the progression criterion.
5. Records the interpretable-vs-kitchen-sink comparison with the full metric
   set for both models (PR-AUC, precision, recall, Brier, leakage verdict).
6. Selects the interpretable primary iff it passes the gate; a failing primary is
   ineligible and is not silently replaced (fixed decision).
7. Builds the online ``FittedScorer`` and a JSON-serialisable ``TrainingReport``.

Nothing here mutates the canonical dataset. The test split is touched
only for final evaluation and the gate — never to tune a parameter or threshold.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd
from pydantic import BaseModel, ConfigDict

from evaluation.calibration_report import CalibrationReport, build_calibration_report
from evaluation.leakage_gate import LeakageVerdict, run_leakage_gate
from evaluation.model_eval import EvalMetrics, compute_metrics
from tfm.config.settings import ModelConfig
from tfm.data.features import COMPARATOR_FEATURE_COLUMNS, PRIMARY_FEATURE_COLUMNS
from tfm.data.splits import make_out_of_time_split
from tfm.ml.calibration import CalibratedModel, choose_and_fit_calibrator
from tfm.ml.candidates import build_candidates
from tfm.ml.model import FittedScorer
from tfm.ml.pipeline import (
    association_directions,
    fit_candidate,
    permutation_importance_pr_auc,
    predict_proba,
)

_TOP_SIGNALS = 5
_LABEL = "label"


class CandidateReport(BaseModel):
    """Per-candidate evaluation record."""

    model_config = ConfigDict(frozen=True)

    name: str
    is_primary: bool
    feature_columns: tuple[str, ...]
    calibration_method: str
    metrics: EvalMetrics
    leakage_verdict: LeakageVerdict | None  # run for the two candidates


class TrainingReport(BaseModel):
    """The full training/evaluation report (JSON-serialisable)."""

    model_config = ConfigDict(frozen=True)

    model_version_id: str
    trained_at: str
    seed: int
    selected_candidate: str
    selected_eligible: bool
    candidate_reports: tuple[CandidateReport, ...]
    df1: dict[str, object]
    calibration: CalibrationReport
    selected_leakage_verdict: LeakageVerdict


@dataclass(frozen=True)
class TrainingOutcome:
    """The training result: the report, the online scorer, and its eligibility."""

    report: TrainingReport
    scorer: FittedScorer
    eligible: bool


def run_training(
    features_df: pd.DataFrame,
    config: ModelConfig,
    *,
    model_version_id: str | None = None,
) -> TrainingOutcome:
    """Run the full bounded candidate comparison and leakage gate on ``features_df``."""
    version_id = model_version_id or f"tfm-scorer-{datetime.now(UTC):%Y%m%d%H%M%S}"

    split = make_out_of_time_split(
        features_df,
        train_end_step=config.split.train_end_step,
        val_end_step=config.split.val_end_step,
    )
    train_df, val_df, test_df = split.train, split.val, split.test
    y_test = test_df[_LABEL].astype(int).to_numpy()

    candidates = build_candidates(PRIMARY_FEATURE_COLUMNS, COMPARATOR_FEATURE_COLUMNS, config.seed)

    reports: list[CandidateReport] = []
    primary_scorer: FittedScorer | None = None
    primary_verdict: LeakageVerdict | None = None
    primary_cal_report: CalibrationReport | None = None

    for spec in candidates:
        fitted = fit_candidate(spec, train_df, _LABEL)

        # Calibrate on val.
        y_val = val_df[_LABEL].astype(int).to_numpy()
        raw_val = predict_proba(fitted, val_df)
        calibrator, method = choose_and_fit_calibrator(raw_val, y_val, config.calibration)
        calibrated_model = CalibratedModel(fitted.estimator, calibrator, method)
        cal_report = build_calibration_report(
            method=method,
            y_true=y_val,
            prob_before=raw_val,
            prob_after=calibrator.predict(raw_val),
        )

        # Evaluate calibrated probabilities on the OOT test split.
        raw_test = predict_proba(fitted, test_df)
        cal_test = calibrator.predict(raw_test)
        metrics = compute_metrics(y_test, cal_test, config.eval_threshold)

        # Leakage gate for the two candidates (interpretable + kitchen-sink).
        verdict: LeakageVerdict | None = None
        if spec.kind in ("histgb", "lightgbm"):
            verdict = run_leakage_gate(
                primary_spec=spec,
                train_df=train_df,
                test_df=test_df,
                balance_artifact_features=config.balance_artifact_features,
                config=config.leakage_gate,
                eval_threshold=config.eval_threshold,
                label_col=_LABEL,
            )

        reports.append(
            CandidateReport(
                name=spec.name,
                is_primary=spec.is_primary,
                feature_columns=spec.feature_columns,
                calibration_method=method,
                metrics=metrics,
                leakage_verdict=verdict,
            )
        )

        if spec.is_primary:
            importances = permutation_importance_pr_auc(
                fitted, val_df, _LABEL, config.leakage_gate.importance_repeats, spec.seed
            )
            top_features = [
                name
                for name, imp in sorted(importances.items(), key=lambda kv: kv[1], reverse=True)
                if imp > 0.0
            ][:_TOP_SIGNALS]
            directions = association_directions(train_df, list(spec.feature_columns), _LABEL)
            primary_scorer = FittedScorer(
                model_version_id=version_id,
                estimator=calibrated_model,
                feature_columns=list(spec.feature_columns),
                preprocessor=fitted.preprocessor,
                signal_top_features=top_features,
                signal_directions=directions,
                calibrated=True,
            )
            primary_verdict = verdict
            primary_cal_report = cal_report

    assert primary_scorer is not None
    assert primary_verdict is not None
    assert primary_cal_report is not None

    df1 = _build_df1(reports)
    eligible = primary_verdict.passed

    report = TrainingReport(
        model_version_id=version_id,
        trained_at=datetime.now(UTC).isoformat(),
        seed=config.seed,
        selected_candidate=primary_scorer.model_version_id,
        selected_eligible=eligible,
        candidate_reports=tuple(reports),
        df1=df1,
        calibration=primary_cal_report,
        selected_leakage_verdict=primary_verdict,
    )
    return TrainingOutcome(report=report, scorer=primary_scorer, eligible=eligible)


def _build_df1(reports: list[CandidateReport]) -> dict[str, object]:
    """Assemble the interpretable-vs-kitchen-sink comparison.

    Both models report PR-AUC, precision, recall, Brier, and the leakage verdict.
    """
    by_kind = {r.name: r for r in reports}
    interp = next((r for r in reports if r.is_primary), None)
    kitchen = next((r for r in reports if r.name == "lightgbm_kitchen_sink"), None)

    def _summary(r: CandidateReport | None) -> dict[str, object]:
        if r is None:
            return {}
        return {
            "name": r.name,
            "pr_auc": r.metrics.pr_auc,
            "precision": r.metrics.precision,
            "recall": r.metrics.recall,
            "brier": r.metrics.brier,
            "leakage_verdict": (r.leakage_verdict.verdict if r.leakage_verdict else None),
        }

    delta = None
    decision = "interpretable primary retained"
    if interp is not None and kitchen is not None:
        delta = float(kitchen.metrics.pr_auc - interp.metrics.pr_auc)
        if delta > 0.05:
            decision = (
                "kitchen-sink shows a material PR-AUC advantage; the interpretability "
                "cost is documented per DF-1 (§11.1). The interpretable primary is still "
                "preferred unless the DF-1 reversal condition is met and recorded."
            )

    return {
        "interpretable": _summary(interp),
        "kitchen_sink": _summary(kitchen),
        "pr_auc_delta_kitchen_minus_interpretable": delta,
        "interpretability_decision": decision,
        "all_candidates": [_summary(by_kind[name]) for name in by_kind],
    }
