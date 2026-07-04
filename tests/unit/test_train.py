"""End-to-end tests for the M2 training pipeline and registry (FR-3/4/22/23/26, DF-1)."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
import pytest

from tfm.config.settings import ModelConfig
from tfm.ml.registry import IneligibleModelError, load_manifest, load_scorer, save_scorer
from tfm.ml.train import run_training
from tfm.schema.evidence import FeatureVector


def test_training_produces_three_candidate_reports(
    make_synth: Callable[..., pd.DataFrame], m2_model_config: ModelConfig
) -> None:
    df = make_synth("behavioural", n=2000, seed=1)
    outcome = run_training(df, m2_model_config, model_version_id="v-test")
    assert len(outcome.report.candidate_reports) == 3
    assert outcome.report.model_version_id == "v-test"


def test_behavioural_primary_is_eligible(
    make_synth: Callable[..., pd.DataFrame], m2_model_config: ModelConfig
) -> None:
    df = make_synth("behavioural", n=2000, seed=1)
    outcome = run_training(df, m2_model_config)
    assert outcome.eligible is True
    assert outcome.report.selected_eligible is True
    assert outcome.report.selected_leakage_verdict.passed


def test_leaky_primary_is_ineligible(
    make_synth: Callable[..., pd.DataFrame], m2_model_config: ModelConfig
) -> None:
    df = make_synth("leaky", n=2000, seed=1)
    outcome = run_training(df, m2_model_config)
    assert outcome.eligible is False
    assert not outcome.report.selected_leakage_verdict.passed


def test_df1_reports_full_metrics_for_both_models(
    make_synth: Callable[..., pd.DataFrame], m2_model_config: ModelConfig
) -> None:
    df = make_synth("behavioural", n=2000, seed=2)
    outcome = run_training(df, m2_model_config)
    df1 = outcome.report.df1
    for side in ("interpretable", "kitchen_sink"):
        summary = df1[side]
        assert isinstance(summary, dict)
        for key in ("pr_auc", "precision", "recall", "brier", "leakage_verdict"):
            assert key in summary


def test_df1_candidates_have_leakage_verdicts_floor_does_not(
    make_synth: Callable[..., pd.DataFrame], m2_model_config: ModelConfig
) -> None:
    df = make_synth("behavioural", n=1600, seed=3)
    outcome = run_training(df, m2_model_config)
    by_name = {r.name: r for r in outcome.report.candidate_reports}
    assert by_name["histgb_interpretable"].leakage_verdict is not None
    assert by_name["lightgbm_kitchen_sink"].leakage_verdict is not None
    assert by_name["logistic_floor"].leakage_verdict is None


def test_training_does_not_mutate_canonical_dataset(
    make_synth: Callable[..., pd.DataFrame], m2_model_config: ModelConfig
) -> None:
    df = make_synth("behavioural", n=1600, seed=4)
    before = df.copy(deep=True)
    run_training(df, m2_model_config)
    pd.testing.assert_frame_equal(df, before)


def test_report_is_json_serialisable(
    make_synth: Callable[..., pd.DataFrame], m2_model_config: ModelConfig
) -> None:
    df = make_synth("behavioural", n=1600, seed=5)
    outcome = run_training(df, m2_model_config)
    payload = outcome.report.model_dump_json()
    assert '"selected_eligible"' in payload


def test_selected_scorer_scores_a_feature_vector(
    make_synth: Callable[..., pd.DataFrame], m2_model_config: ModelConfig
) -> None:
    df = make_synth("behavioural", n=1600, seed=6)
    outcome = run_training(df, m2_model_config)
    fv = FeatureVector(
        txn_id="t1",
        account_id="C1",
        counterparty_id="X1",
        amount=1000.0,
        type_payment=False,
        type_transfer=True,
        type_cash_out=False,
        type_cash_in=False,
        type_debit=False,
        bal_orig_before=2000.0,
        bal_orig_after=0.0,
        bal_dest_before=None,
        bal_dest_after=None,
        frac_bal_orig_moved=0.5,
        orig_account_emptied=True,
        txn_count_24h=6,
        amount_sum_24h=3000.0,
        is_new_counterparty=True,
        distinct_counterparties_seen=3,
    )
    score = outcome.scorer.score(fv)
    assert 0.0 <= score.probability <= 1.0
    assert score.calibrated is True


# ── Registry (FR-4) ────────────────────────────────────────────────────────────


def test_registry_round_trip_eligible(
    make_synth: Callable[..., pd.DataFrame], m2_model_config: ModelConfig, tmp_path
) -> None:
    df = make_synth("behavioural", n=1600, seed=7)
    outcome = run_training(df, m2_model_config)
    path = tmp_path / "scorer.joblib"
    save_scorer(outcome.scorer, leakage_passed=True, manifest={"k": "v"}, path=path)

    loaded = load_scorer(path, require_pass=True)
    assert loaded.model_version_id == outcome.scorer.model_version_id
    assert load_manifest(path) == {"k": "v"}


def test_registry_refuses_ineligible_in_online_path(
    make_synth: Callable[..., pd.DataFrame], m2_model_config: ModelConfig, tmp_path
) -> None:
    df = make_synth("behavioural", n=1200, seed=8)
    outcome = run_training(df, m2_model_config)
    path = tmp_path / "scorer.joblib"
    save_scorer(outcome.scorer, leakage_passed=False, manifest={}, path=path)

    with pytest.raises(IneligibleModelError):
        load_scorer(path, require_pass=True)
    # Offline inspection may still load it.
    assert load_scorer(path, require_pass=False).model_version_id is not None


def test_load_model_config_from_real_yaml() -> None:
    from tfm.config.settings import Settings, load_model_config

    config = load_model_config(Settings(config_dir="config"))
    assert config.split.train_end_step == 500
    assert config.split.val_end_step == 580
    assert "orig_account_emptied" in config.balance_artifact_features


# ── Feature-set coherence (IMP-011) ─────────────────────────────────────────────


def test_primary_columns_exclude_balance_artifacts() -> None:
    """PRIMARY_FEATURE_COLUMNS excludes exactly the configured balance artifacts.

    Binds the explicit code lists to the gate's configured
    ``balance_artifact_features`` so quarantine and the gate cannot drift apart.
    """
    from tfm.config.settings import Settings, load_model_config
    from tfm.data.features import FEATURE_COLUMNS, PRIMARY_FEATURE_COLUMNS

    config = load_model_config(Settings(config_dir="config"))
    artifacts = set(config.balance_artifact_features)
    assert set(PRIMARY_FEATURE_COLUMNS).isdisjoint(artifacts)
    assert set(FEATURE_COLUMNS) == set(PRIMARY_FEATURE_COLUMNS) | artifacts


def test_comparator_columns_are_canonical_plus_augmented() -> None:
    from tfm.config.settings import Settings, load_model_config
    from tfm.data.features import COMPARATOR_FEATURE_COLUMNS, FEATURE_COLUMNS

    config = load_model_config(Settings(config_dir="config"))
    expected = set(FEATURE_COLUMNS) | set(config.augmented_features)
    assert set(COMPARATOR_FEATURE_COLUMNS) == expected


def test_primary_report_excludes_balance_artifacts(
    make_synth: Callable[..., pd.DataFrame], m2_model_config: ModelConfig
) -> None:
    """The shipped interpretable primary trains on the behavioural substrate only."""
    df = make_synth("behavioural", n=1200, seed=5)
    outcome = run_training(df, m2_model_config)
    by_name = {r.name: r for r in outcome.report.candidate_reports}
    primary_cols = set(by_name["histgb_interpretable"].feature_columns)
    assert primary_cols.isdisjoint(m2_model_config.balance_artifact_features)
