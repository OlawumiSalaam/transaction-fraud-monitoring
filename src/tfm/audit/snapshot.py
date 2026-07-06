"""The immutable decision snapshot written to the audit log.

One ``disposition_recorded`` event carries the complete, self-contained record of
an analyst decision — the "what was shown", "what was decided", and "what
resulted" — as a **versioned, immutable snapshot**. Reconstruction (``reconstruct``)
deserializes this and nothing else: no rule engine, recommendation policy,
explanation generation, grounding, or configuration is ever re-invoked.

Why snapshot the *rendered* artifacts rather than inputs + config: the templated
explanation copy, rule parameters, and thresholds may change over time (the
reword is a concrete example). Re-deriving would then reproduce *today's* output,
not what the analyst saw. Storing the rendered `EvidencePackage`, `Recommendation`,
and `Explanation` makes reconstruction immune to any future change in decision logic.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from tfm.explanation.explainer import Explanation
from tfm.recommendation.policy import Recommendation
from tfm.schema.evidence import EvidencePackage

# Bump only on a breaking change to the snapshot shape; reconstruction can then
# branch on it. V1 ships version 1.
SNAPSHOT_VERSION = 1


class DispositionSnapshot(BaseModel):
    """The analyst's decision, frozen."""

    model_config = ConfigDict(frozen=True)

    action: str
    reason_code: str
    rationale: str | None
    deviated_from_recommendation: bool
    follow_up: str | None


class RoutingSnapshot(BaseModel):
    """The routing state as decided at disposition time.

    This is the routing *decision*, not the case's live status (which continues to
    change afterwards and is intentionally a live reference, not part of the record).
    """

    model_config = ConfigDict(frozen=True)

    status: str  # cleared | pending | escalated
    routed_to: str  # closed | pending review | escalation


class Provenance(BaseModel):
    """Attribution stamps — for lineage, never for recomputation."""

    model_config = ConfigDict(frozen=True)

    snapshot_version: int
    model_version_id: str | None
    score_available: bool
    score_band: str
    explainer_pathway: str


class DecisionSnapshot(BaseModel):
    """The complete, self-contained record of one analyst decision.

    Everything needed to explain the action is embedded here; reconstruction never
    reads ``cases``, ``dispositions``, ``transactions``, ``rule_hits``, or config.
    """

    model_config = ConfigDict(frozen=True)

    snapshot_version: int
    case_id: str
    txn_id: str
    analyst_id: str
    recorded_at: str  # ISO-8601

    # Immutable snapshots of exactly what the analyst saw ( artifacts).
    evidence: EvidencePackage
    recommendation: Recommendation
    explanation: Explanation

    # The decision and its result.
    disposition: DispositionSnapshot
    routing: RoutingSnapshot

    provenance: Provenance


def build_decision_snapshot(
    *,
    case_id: str,
    txn_id: str,
    analyst_id: str,
    recorded_at: str,
    evidence: EvidencePackage,
    recommendation: Recommendation,
    explanation: Explanation,
    action: str,
    reason_code: str,
    rationale: str | None,
    deviated_from_recommendation: bool,
    follow_up: str | None,
    status: str,
    routed_to: str,
    model_version_id: str | None,
    score_available: bool,
    score_band: str,
) -> DecisionSnapshot:
    """Assemble the immutable snapshot from the artifacts shown + the decision."""
    return DecisionSnapshot(
        snapshot_version=SNAPSHOT_VERSION,
        case_id=case_id,
        txn_id=txn_id,
        analyst_id=analyst_id,
        recorded_at=recorded_at,
        evidence=evidence,
        recommendation=recommendation,
        explanation=explanation,
        disposition=DispositionSnapshot(
            action=action,
            reason_code=reason_code,
            rationale=rationale,
            deviated_from_recommendation=deviated_from_recommendation,
            follow_up=follow_up,
        ),
        routing=RoutingSnapshot(status=status, routed_to=routed_to),
        provenance=Provenance(
            snapshot_version=SNAPSHOT_VERSION,
            model_version_id=model_version_id,
            score_available=score_available,
            score_band=score_band,
            explainer_pathway=explanation.pathway,
        ),
    )
