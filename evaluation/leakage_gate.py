"""Simulator-leakage gate — the M2 progression criterion (FR-4, FR-26, §9).

The gate answers one question: **has the model learned behavioural fraud
patterns, or merely bookkeeping (balance-consistency) artefacts?** PaySim's
balance-update artefacts can nearly separate fraud on their own (§9), so a model
that rides them would post strong headline metrics while learning nothing
transferable.

The verdict is **evidence-based** (IMP-007). The gate assembles three strands of
evidence and derives the conclusion from them together:

1. **Ablation** — retrain the same architecture with the balance-artifact
   features removed; measure the PR-AUC delta.
2. **Feature-importance inspection** — permutation importances of the full model,
   showing whether balance-artifact features dominate.
3. **Remaining behavioural performance** — the ablated model's absolute PR-AUC,
   showing whether genuine behavioural signal survives without the artefacts.

Any numeric thresholds are configurable decision-support defaults
(``config/model.yaml`` → ``leakage_gate``); they support the verdict but do not
define it. The full evidence and a human-readable rationale are always recorded.

A ``fail`` model is ineligible (FR-4) regardless of headline metrics. If
remediation is impossible within the submission window, the failure ships
documented — never hidden (M2 fixed decision).

Spec references: FR-4, FR-26, §9; Addendum §5 (R3); IMP-007.
"""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
from pydantic import BaseModel, ConfigDict

from tfm.config.settings import LeakageGateConfig
from tfm.ml.candidates import CandidateSpec
from tfm.ml.pipeline import (
    fit_candidate,
    permutation_importance_pr_auc,
    predict_proba,
)

from .model_eval import EvalMetrics, compute_metrics


class FeatureImportance(BaseModel):
    """One feature's permutation importance (PR-AUC drop when shuffled)."""

    model_config = ConfigDict(frozen=True)

    name: str
    importance: float


class LeakageEvidence(BaseModel):
    """The full evidence body behind a leakage verdict (IMP-007)."""

    model_config = ConfigDict(frozen=True)

    full_metrics: EvalMetrics
    ablated_metrics: EvalMetrics
    pr_auc_delta: float  # full.pr_auc - ablated.pr_auc
    remaining_behavioural_pr_auc: float  # ablated.pr_auc
    balance_artifact_features: tuple[str, ...]
    balance_artifact_importance_share: float
    top_importances: tuple[FeatureImportance, ...]


class LeakageVerdict(BaseModel):
    """The gate result: verdict + evidence + applied defaults + rationale."""

    model_config = ConfigDict(frozen=True)

    verdict: str  # "pass" | "fail"
    rationale: str
    evidence: LeakageEvidence
    applied_defaults: dict[str, float]

    @property
    def passed(self) -> bool:
        return self.verdict == "pass"

    def summary_string(self) -> str:
        """Compact one-line record for ``model_versions.leakage_verdict`` (TEXT)."""
        return (
            f"{self.verdict}: ablation_delta_pr_auc="
            f"{self.evidence.pr_auc_delta:.4f}; "
            f"remaining_behavioural_pr_auc="
            f"{self.evidence.remaining_behavioural_pr_auc:.4f}"
        )


def _importance_share(importances: dict[str, float], artifact_features: list[str]) -> float:
    """Share of total positive permutation importance held by artifact features."""
    positive = {k: max(v, 0.0) for k, v in importances.items()}
    total = sum(positive.values())
    if total <= 0.0:
        return 0.0
    artifact_total = sum(positive.get(f, 0.0) for f in artifact_features)
    return artifact_total / total


def run_leakage_gate(
    *,
    primary_spec: CandidateSpec,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    balance_artifact_features: list[str],
    config: LeakageGateConfig,
    eval_threshold: float,
    label_col: str = "label",
) -> LeakageVerdict:
    """Run the leakage gate for one model architecture and return the verdict.

    Trains the full model and the ablated (balance-artifact-free) model on the
    training split, evaluates both on the out-of-time test split, inspects
    permutation importances, and derives an evidence-based verdict.
    """
    # 1. Full model and ablated model (same architecture, reduced feature set).
    full = fit_candidate(primary_spec, train_df, label_col)
    reduced = [c for c in primary_spec.feature_columns if c not in balance_artifact_features]
    ablated_spec = replace(
        primary_spec,
        name=f"{primary_spec.name}_ablated",
        feature_columns=tuple(reduced),
        is_primary=False,
    )
    ablated = fit_candidate(ablated_spec, train_df, label_col)

    y_test = test_df[label_col].astype(int).to_numpy()
    full_metrics = compute_metrics(y_test, predict_proba(full, test_df), eval_threshold)
    ablated_metrics = compute_metrics(y_test, predict_proba(ablated, test_df), eval_threshold)

    # 2. Feature-importance inspection (permutation importance on the OOT test).
    importances = permutation_importance_pr_auc(
        full, test_df, label_col, config.importance_repeats, primary_spec.seed
    )
    ranked = sorted(importances.items(), key=lambda kv: kv[1], reverse=True)
    top_importances = tuple(FeatureImportance(name=n, importance=v) for n, v in ranked)
    artifact_share = _importance_share(importances, balance_artifact_features)

    # 3. Assemble evidence.
    delta = float(full_metrics.pr_auc - ablated_metrics.pr_auc)
    remaining = float(ablated_metrics.pr_auc)
    evidence = LeakageEvidence(
        full_metrics=full_metrics,
        ablated_metrics=ablated_metrics,
        pr_auc_delta=delta,
        remaining_behavioural_pr_auc=remaining,
        balance_artifact_features=tuple(balance_artifact_features),
        balance_artifact_importance_share=artifact_share,
        top_importances=top_importances,
    )

    applied_defaults = {
        "min_behavioural_pr_auc": config.min_behavioural_pr_auc,
        "max_ablation_pr_auc_delta": config.max_ablation_pr_auc_delta,
        "importance_repeats": float(config.importance_repeats),
    }

    verdict, rationale = _derive_verdict(evidence, config)
    return LeakageVerdict(
        verdict=verdict,
        rationale=rationale,
        evidence=evidence,
        applied_defaults=applied_defaults,
    )


def _derive_verdict(evidence: LeakageEvidence, config: LeakageGateConfig) -> tuple[str, str]:
    """Derive an evidence-based verdict and its rationale (IMP-007).

    Two evidence dimensions support the conclusion: (a) whether behavioural signal
    survives ablation (remaining PR-AUC), and (b) how much performance depended on
    the balance artefacts (ablation delta). The configured numbers are the applied
    decision-support defaults, cited in the rationale — not the definition.
    """
    remaining = evidence.remaining_behavioural_pr_auc
    delta = evidence.pr_auc_delta
    share = evidence.balance_artifact_importance_share

    if remaining != remaining:  # NaN guard (degenerate single-class test split)
        return (
            "fail",
            "Insufficient class balance in the out-of-time test split to evaluate "
            "behavioural performance; the gate cannot certify the model as learning "
            "behavioural patterns and it is therefore ineligible (FR-4).",
        )

    behavioural_survives = remaining >= config.min_behavioural_pr_auc
    modest_dependence = delta <= config.max_ablation_pr_auc_delta

    if behavioural_survives and modest_dependence:
        return (
            "pass",
            (
                f"Behavioural signal survives ablation: with the balance-artifact "
                f"features {list(evidence.balance_artifact_features)} removed, the model "
                f"retains PR-AUC {remaining:.4f} (≥ decision-support default "
                f"{config.min_behavioural_pr_auc:.2f}), and full-model performance falls "
                f"by only {delta:.4f} PR-AUC (≤ default {config.max_ablation_pr_auc_delta:.2f}). "
                f"Balance-artifact features hold {share:.1%} of total permutation "
                f"importance. The evidence indicates the model learned behavioural fraud "
                f"patterns rather than bookkeeping artefacts. Verdict: PASS (eligible, FR-4)."
            ),
        )

    reasons: list[str] = []
    if not behavioural_survives:
        reasons.append(
            f"behavioural performance collapses without the balance artefacts "
            f"(remaining PR-AUC {remaining:.4f} < default "
            f"{config.min_behavioural_pr_auc:.2f})"
        )
    if not modest_dependence:
        reasons.append(
            f"full-model performance depends heavily on the balance artefacts "
            f"(ablation delta {delta:.4f} > default "
            f"{config.max_ablation_pr_auc_delta:.2f})"
        )
    return (
        "fail",
        (
            f"The model appears to ride balance-consistency artefacts: "
            f"{'; '.join(reasons)}. Balance-artifact features hold {share:.1%} of total "
            f"permutation importance. Under FR-4/FR-26 the model is ineligible regardless "
            f"of its headline metrics; remediation (feature curation / model change) is "
            f"required before it can advance. Verdict: FAIL."
        ),
    )
