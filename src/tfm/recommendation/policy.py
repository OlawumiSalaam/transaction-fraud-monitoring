"""Recommendation Policy: (score band, rule hits) -> clear/hold/escalate.

A pure, deterministic, **advisory** mapping from the score band plus the fired rule
hits to a suggested action. It never decides — the analyst is the sole decider
(Decision A/C) — and it does not score, explain, rank, or route.

Two paths, one architecture:

- **Absent-score path (operational; ships while the scorer is gate-ineligible):**
  recommends solely from rule evidence and **never returns ``clear``** — a
  clear asserts trustworthy low-risk assurance the excluded scorer cannot provide.
  An escalating rule -> escalate; any other fired rule -> hold; no rule hits -> hold
  with the uncertainty flag set. ``score_band`` is ``"none"``.
- **Present-score path (future-ready; not exercised operationally):** the standard
  (band x rule signal) mapping, taking the most severe of the score and rule
  signals; borderline floors at hold. Introducing an eligible scorer later flips
  ``ScoreStatus.available`` and activates this path with no policy change.

Thresholds and the escalating-rule set come from ``config/thresholds.yaml`` (no
literals in logic). The recommendation carries its basis (score band + rule ids)
and an uncertainty flag.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

from tfm.config.settings import ScoreBandsConfig, ThresholdsConfig
from tfm.schema.evidence import RuleHit, ScoreStatus

Action = Literal["clear", "hold", "escalate"]
Confidence = Literal["low", "medium", "high"]
ScoreBand = Literal["low", "borderline", "high", "none"]

_SEVERITY: dict[Action, int] = {"clear": 0, "hold": 1, "escalate": 2}
_BAND_ACTION: dict[ScoreBand, Action] = {
    "low": "clear",
    "borderline": "hold",
    "high": "escalate",
}


class RecommendationBasis(BaseModel):
    """What the recommendation was derived from — auditable."""

    model_config = ConfigDict(frozen=True)

    score_band: ScoreBand
    rule_ids: tuple[str, ...]


class Recommendation(BaseModel):
    """The advisory recommendation. Never a decision."""

    model_config = ConfigDict(frozen=True)

    action: Action
    confidence: Confidence
    basis: RecommendationBasis
    uncertainty_flag: bool


def _score_band(probability: float, bands: ScoreBandsConfig) -> ScoreBand:
    if probability < bands.low_max:
        return "low"
    if probability >= bands.high_min:
        return "high"
    return "borderline"


def _rule_action(rule_ids: tuple[str, ...], escalating: frozenset[str]) -> Action | None:
    """The action implied by the fired rules, or None when no rule fired."""
    if not rule_ids:
        return None
    if any(rid in escalating for rid in rule_ids):
        return "escalate"
    return "hold"


def recommend(
    *,
    score: ScoreStatus,
    rule_hits: Sequence[RuleHit],
    config: ThresholdsConfig,
) -> Recommendation:
    """Map (score band, rule hits) to an advisory clear/hold/escalate recommendation.

    Pure, deterministic, and total over every (score band x rule-hit) combination.
    Advisory only — the disposition remains the analyst's (never pre-selected here).
    """
    rule_ids = tuple(hit.rule_id for hit in rule_hits)
    escalating = frozenset(config.recommendation.escalating_rules)
    rule_action = _rule_action(rule_ids, escalating)

    band: ScoreBand
    action: Action
    confidence: Confidence

    if score.available and score.probability is not None:
        band = _score_band(score.probability, config.score_bands)
        score_action = _BAND_ACTION[band]
        candidates: list[Action] = [score_action]
        if rule_action is not None:
            candidates.append(rule_action)
        action = max(candidates, key=lambda a: _SEVERITY[a])
        conflict = rule_action is not None and rule_action != score_action
        uncertainty_flag = band == "borderline" or conflict
        confidence = "high" if (band in ("low", "high") and not conflict) else "medium"
    else:
        # Absent-score path: never clear( — no trustworthy assurance of safety).
        band = "none"
        action = rule_action if rule_action is not None else "hold"
        uncertainty_flag = True  # no operational score to corroborate
        confidence = "medium" if rule_action is not None else "low"

    return Recommendation(
        action=action,
        confidence=confidence,
        basis=RecommendationBasis(score_band=band, rule_ids=rule_ids),
        uncertainty_flag=uncertainty_flag,
    )
