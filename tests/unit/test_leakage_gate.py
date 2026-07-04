"""Unit tests for the simulator-leakage gate (FR-4, FR-26, §9).

The gate must reach the correct evidence-based verdict in both directions:

- a *behavioural* dataset (fraud driven by behavioural features; balance
  artifacts are noise) must PASS — behavioural signal survives ablation;
- a *leaky* dataset (fraud driven almost entirely by a balance artifact) must
  FAIL — performance collapses when the artifacts are removed.

This is the credibility-critical test of M2.
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from evaluation.leakage_gate import LeakageVerdict, run_leakage_gate
from tfm.config.settings import ModelConfig
from tfm.data.features import FEATURE_COLUMNS
from tfm.data.splits import make_out_of_time_split
from tfm.ml.candidates import build_candidates


def _run_gate(df: pd.DataFrame, config: ModelConfig) -> LeakageVerdict:
    split = make_out_of_time_split(
        df,
        train_end_step=config.split.train_end_step,
        val_end_step=config.split.val_end_step,
    )
    primary = build_candidates(FEATURE_COLUMNS, config.augmented_features, config.seed)[0]
    return run_leakage_gate(
        primary_spec=primary,
        train_df=split.train,
        test_df=split.test,
        balance_artifact_features=config.balance_artifact_features,
        config=config.leakage_gate,
        eval_threshold=config.eval_threshold,
    )


def test_behavioural_model_passes_gate(
    make_synth: Callable[..., pd.DataFrame], m2_model_config: ModelConfig
) -> None:
    df = make_synth("behavioural", n=2000, seed=1)
    verdict = _run_gate(df, m2_model_config)
    assert verdict.passed, verdict.rationale
    # Behavioural signal survives ablation.
    assert verdict.evidence.remaining_behavioural_pr_auc >= (
        m2_model_config.leakage_gate.min_behavioural_pr_auc
    )
    assert "PASS" in verdict.rationale


def test_leaky_model_fails_gate(
    make_synth: Callable[..., pd.DataFrame], m2_model_config: ModelConfig
) -> None:
    df = make_synth("leaky", n=2000, seed=1)
    verdict = _run_gate(df, m2_model_config)
    assert not verdict.passed, verdict.rationale
    # Removing the artifacts collapses behavioural performance.
    assert (
        verdict.evidence.remaining_behavioural_pr_auc
        < m2_model_config.leakage_gate.min_behavioural_pr_auc
    )
    assert "FAIL" in verdict.rationale


def test_leaky_model_shows_artifact_importance(
    make_synth: Callable[..., pd.DataFrame], m2_model_config: ModelConfig
) -> None:
    df = make_synth("leaky", n=2000, seed=2)
    verdict = _run_gate(df, m2_model_config)
    # Balance-artifact features should carry a substantial importance share.
    assert verdict.evidence.balance_artifact_importance_share > 0.5


def test_verdict_carries_full_evidence(
    make_synth: Callable[..., pd.DataFrame], m2_model_config: ModelConfig
) -> None:
    df = make_synth("behavioural", n=1600, seed=3)
    verdict = _run_gate(df, m2_model_config)
    ev = verdict.evidence
    assert len(ev.top_importances) == len(FEATURE_COLUMNS)
    assert set(ev.balance_artifact_features) == set(m2_model_config.balance_artifact_features)
    assert verdict.applied_defaults["min_behavioural_pr_auc"] == 0.50
    # Compact record for the model_versions row.
    assert verdict.summary_string().startswith(("pass", "fail"))


def test_verdict_is_frozen(
    make_synth: Callable[..., pd.DataFrame], m2_model_config: ModelConfig
) -> None:
    import pytest
    from pydantic import ValidationError

    df = make_synth("behavioural", n=1200, seed=4)
    verdict = _run_gate(df, m2_model_config)
    with pytest.raises(ValidationError):
        verdict.verdict = "fail"  # type: ignore[misc]
