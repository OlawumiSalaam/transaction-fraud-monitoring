"""M9 offline-evaluation tests (§7, §8; FR-22/24/26).

Confirms: the consolidated report reads the committed M2 metrics **verbatim** (not
regenerated), the leakage verdict is surfaced alongside the headline metrics, every
number is labelled measured/modelled-estimate, grounding is ≈0 ungrounded on the
templated floor, and the manifest is a single source of truth for packaging.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evaluation.grounding_report import build_grounding_report
from evaluation.labels import Label
from evaluation.run_all import build_manifest, build_summary
from tfm.ml.registry import load_manifest


@pytest.fixture(scope="module")
def summary() -> dict:
    return build_summary()


@pytest.fixture(scope="module")
def grounding() -> dict:
    return build_grounding_report()


def test_grounding_report_zero_ungrounded_on_templated_floor(grounding: dict) -> None:
    assert grounding["n_cases"] == 6
    ungrounded = grounding["ungrounded_statement_rate"]
    assert ungrounded["value"] == 0.0
    assert ungrounded["label"] == Label.MEASURED


def test_summary_metrics_are_committed_m2_values_verbatim(summary: dict) -> None:
    committed = load_manifest(Path("models/scorer.joblib"))["metrics"]
    reported = summary["headline"]["metrics"]
    for key in ("pr_auc", "precision", "recall", "roc_auc", "brier"):
        # Identical to the committed artifact — read, not regenerated or rounded.
        assert reported[key]["value"] == committed[key]


def test_leakage_verdict_surfaced_alongside_metrics(summary: dict) -> None:
    head = summary["headline"]
    assert summary["leakage_verdict"] == "fail"
    assert head["leakage_verdict"] == "fail"
    assert head["scorer_eligible"] is False
    assert "FAIL" in head["status"]  # impossible to miss when reading the numbers
    for metric in head["metrics"].values():
        assert metric["label"] == Label.MODELLED_ESTIMATE


def test_every_reported_metric_is_labelled(summary: dict) -> None:
    labelled = [
        *summary["headline"]["metrics"].values(),
        summary["calibration"]["brier"],
        summary["grounding"]["ungrounded_statement_rate"],
        summary["grounding"]["templated_fallback_rate"],
        summary["grounding"]["total_ungrounded_tokens"],
    ]
    for metric in labelled:
        assert metric["label"] in {Label.MEASURED, Label.MODELLED_ESTIMATE}


def test_manifest_is_single_source_of_truth(summary: dict) -> None:
    manifest = build_manifest(summary)
    for key in (
        "generated_at",
        "model_version_id",
        "dataset",
        "leakage_verdict",
        "scorer_eligible",
        "artifacts",
    ):
        assert key in manifest
    names = {a["name"] for a in manifest["artifacts"]}
    assert {
        "evaluation_summary",
        "grounding_report",
        "training_report",
        "leakage_verdict",
        "model_artifact",
    } <= names
    training = next(a for a in manifest["artifacts"] if a["name"] == "training_report")
    assert manifest["model_version_id"] in training["path"]  # derived, not hardcoded
