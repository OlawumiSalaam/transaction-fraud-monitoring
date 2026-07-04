"""Unit tests for the Recommendation Policy (FR-8, FR-9, M5).

Covers the (score band x rule-hit) truth table with totality, borderline -> hold,
the absent-score operational path (never clear), config-sourced escalation, and
the basis / uncertainty flag.

Spec: FR-8, FR-9, §11.2; Addendum §4; Implementation Plan M5.
"""

from __future__ import annotations

import pytest

from tfm.config.settings import (
    RecommendationConfig,
    ScoreBandsConfig,
    Settings,
    ThresholdsConfig,
    load_config,
)
from tfm.recommendation.policy import recommend
from tfm.schema.evidence import RuleHit, ScoreStatus


def _config(escalating: tuple[str, ...] = ("account_draining",)) -> ThresholdsConfig:
    return ThresholdsConfig(
        score_bands=ScoreBandsConfig(low_max=0.30, high_min=0.80),
        recommendation=RecommendationConfig(escalating_rules=list(escalating)),
    )


def _excluded() -> ScoreStatus:
    return ScoreStatus(
        available=False,
        model_version_id="tfm-scorer-20260704053632",
        leakage_verdict="fail",
        exclusion_reason="excluded under FR-4",
    )


def _scored(probability: float) -> ScoreStatus:
    return ScoreStatus(
        available=True, model_version_id="v", probability=probability, calibrated=True
    )


def _hit(rule_id: str) -> RuleHit:
    return RuleHit(rule_id=rule_id, summary="s", evidence={})


# ── Absent-score operational path ─────────────────────────────────────────────


def test_absent_score_escalating_rule_escalates() -> None:
    rec = recommend(score=_excluded(), rule_hits=[_hit("account_draining")], config=_config())
    assert rec.action == "escalate"
    assert rec.basis.score_band == "none"
    assert rec.uncertainty_flag is True
    assert rec.basis.rule_ids == ("account_draining",)


def test_absent_score_non_escalating_rule_holds() -> None:
    rec = recommend(score=_excluded(), rule_hits=[_hit("new_beneficiary_large")], config=_config())
    assert rec.action == "hold"
    assert rec.uncertainty_flag is True


def test_absent_score_no_rules_holds_with_low_confidence() -> None:
    rec = recommend(score=_excluded(), rule_hits=[], config=_config())
    assert rec.action == "hold"
    assert rec.confidence == "low"
    assert rec.uncertainty_flag is True


@pytest.mark.parametrize(
    "rule_hits",
    [
        [],
        [_hit("new_beneficiary_large")],
        [_hit("account_draining")],
        [_hit("account_draining"), _hit("new_beneficiary_large")],
    ],
)
def test_absent_score_never_clears(rule_hits: list[RuleHit]) -> None:
    rec = recommend(score=_excluded(), rule_hits=rule_hits, config=_config())
    assert rec.action in {"hold", "escalate"}
    assert rec.action != "clear"


# ── Present-score path (future-ready) ─────────────────────────────────────────


def test_present_low_no_rules_clears() -> None:
    rec = recommend(score=_scored(0.05), rule_hits=[], config=_config())
    assert rec.action == "clear"
    assert rec.basis.score_band == "low"
    assert rec.uncertainty_flag is False


def test_present_high_escalates() -> None:
    rec = recommend(score=_scored(0.95), rule_hits=[], config=_config())
    assert rec.action == "escalate"
    assert rec.basis.score_band == "high"


@pytest.mark.parametrize("rule_hits", [[], [_hit("new_beneficiary_large")]])
def test_present_borderline_defaults_to_hold(rule_hits: list[RuleHit]) -> None:
    rec = recommend(score=_scored(0.50), rule_hits=rule_hits, config=_config())
    assert rec.action == "hold"
    assert rec.basis.score_band == "borderline"
    assert rec.uncertainty_flag is True


def test_present_low_with_escalating_rule_escalates_and_flags_conflict() -> None:
    rec = recommend(score=_scored(0.05), rule_hits=[_hit("account_draining")], config=_config())
    assert rec.action == "escalate"  # rule overrides the low score band
    assert rec.uncertainty_flag is True  # score/rule conflict


# ── Totality over (band x rule signal) ────────────────────────────────────────


@pytest.mark.parametrize("score", ["excluded", 0.05, 0.50, 0.95])
@pytest.mark.parametrize("rule_hits", [(), ("new_beneficiary_large",), ("account_draining",)])
def test_policy_is_total(score: object, rule_hits: tuple[str, ...]) -> None:
    status = _excluded() if score == "excluded" else _scored(float(score))  # type: ignore[arg-type]
    rec = recommend(score=status, rule_hits=[_hit(r) for r in rule_hits], config=_config())
    assert rec.action in {"clear", "hold", "escalate"}
    assert rec.confidence in {"low", "medium", "high"}
    if not status.available:
        assert rec.action != "clear"


# ── Config-sourced escalation ─────────────────────────────────────────────────


def test_escalation_is_config_driven() -> None:
    # With no escalating rules, account_draining -> hold (not escalate).
    rec = recommend(score=_excluded(), rule_hits=[_hit("account_draining")], config=_config(()))
    assert rec.action == "hold"
    # Promote new_beneficiary_large -> that hit now escalates.
    rec2 = recommend(
        score=_excluded(),
        rule_hits=[_hit("new_beneficiary_large")],
        config=_config(("new_beneficiary_large",)),
    )
    assert rec2.action == "escalate"


def test_shipped_thresholds_config_loads_escalating_rules() -> None:
    config = load_config(Settings(config_dir="config"))
    assert "account_draining" in config.thresholds.recommendation.escalating_rules


def test_determinism() -> None:
    args = {"score": _excluded(), "rule_hits": [_hit("account_draining")], "config": _config()}
    assert recommend(**args) == recommend(**args)  # type: ignore[arg-type]
