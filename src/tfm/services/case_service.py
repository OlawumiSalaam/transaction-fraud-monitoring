"""Case service: assemble+persist cases and serve the composed case view (M7).

Orchestrates the online path — it composes M1–M6 outputs and persists the case;
it adds no fraud, model, or explanation logic. The case view embeds the M4/M5/M6
objects verbatim (boundaries preserved) and rebuilds the explanation deterministically
on read (a pure re-run of M6, not new logic).

Spec references: FR-2, FR-15; Addendum §2.3, §4.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from tfm.api.schemas import CaseView, DrillDownResponse, TransactionFacts
from tfm.assembly.assembler import assemble_evidence
from tfm.config.settings import AppConfig
from tfm.explanation.explainer import explain
from tfm.persistence.models import Case as CaseModel
from tfm.persistence.models import RuleHit as RuleHitModel
from tfm.recommendation.policy import Recommendation, RecommendationBasis, recommend
from tfm.rules.engine import RuleEngine
from tfm.schema.entities import Counterparty, Transaction
from tfm.schema.evidence import EvidencePackage, FeatureVector, ScoreStatus
from tfm.services.errors import CaseNotFound, ElementNotFound

_PRIORITY = {"escalate": 2.0, "hold": 1.0, "clear": 0.0}


def assemble_and_persist_case(
    session: Session,
    *,
    transaction: Transaction,
    features: FeatureVector,
    prior_transaction_count: int,
    counterparty: Counterparty,
    score: ScoreStatus,
    config: AppConfig,
    llm_enabled: bool = False,
) -> CaseModel:
    """Run rules → assemble → recommend → explain, and persist a queued Case."""
    rule_hits = RuleEngine(config.rules).evaluate(features)
    package = assemble_evidence(
        transaction=transaction,
        features=features,
        prior_transaction_count=prior_transaction_count,
        counterparty=counterparty,
        score=score,
        rule_hits=rule_hits,
    )
    recommendation = recommend(score=score, rule_hits=rule_hits, config=config.thresholds)
    explanation = explain(package, recommendation, llm_enabled=llm_enabled)

    now = datetime.now(UTC)
    case = CaseModel(
        case_id=str(uuid.uuid4()),
        txn_id=transaction.txn_id,
        model_version_id=None,  # excluded scorer is captured in the evidence, not as an FK
        score=score.probability if score.available else None,
        score_band=recommendation.basis.score_band,
        recommendation_action=recommendation.action,
        recommendation_confidence=recommendation.confidence,
        recommendation_basis=recommendation.basis.model_dump(),
        uncertainty_flag=recommendation.uncertainty_flag,
        evidence=package.model_dump(mode="json"),
        explanation_text=explanation.text,
        explanation_pathway=explanation.pathway,
        status="queued",
        queue_priority=_PRIORITY.get(recommendation.action, 0.0),
        created_at=now,
    )
    session.add(case)
    for hit in rule_hits:
        session.add(
            RuleHitModel(
                rule_hit_id=str(uuid.uuid4()),
                case_id=case.case_id,
                rule_id=hit.rule_id,
                evidence=dict(hit.evidence),
                created_at=now,
            )
        )
    session.flush()
    return case


def _recommendation(case: CaseModel) -> Recommendation:
    return Recommendation(
        action=case.recommendation_action,  # type: ignore[arg-type]
        confidence=case.recommendation_confidence,  # type: ignore[arg-type]
        basis=RecommendationBasis(**case.recommendation_basis),
        uncertainty_flag=case.uncertainty_flag,
    )


def _transaction_facts(package: EvidencePackage) -> TransactionFacts:
    by_id = {e.element_id: e for e in package.elements}
    facts = by_id["txn_facts"].raw
    direction = str(by_id["direction_balances"].raw.get("direction", ""))
    return TransactionFacts(
        txn_id=str(facts["txn_id"]),
        amount=float(facts["amount"]),  # type: ignore[arg-type]
        type=str(facts["type"]),
        event_ts=str(facts["event_ts"]),
        account_id=str(facts["account_id"]),
        counterparty_id=str(facts["counterparty_id"]),
        direction=direction,
    )


def get_case_view(session: Session, case_id: str, *, llm_enabled: bool = False) -> CaseView:
    """Return the composed case view; rebuild the explanation deterministically (M6)."""
    case = session.get(CaseModel, case_id)
    if case is None:
        raise CaseNotFound(f"case not found: {case_id}", {"case_id": case_id})
    package = EvidencePackage.model_validate(case.evidence)
    recommendation = _recommendation(case)
    explanation = explain(package, recommendation, llm_enabled=llm_enabled)
    return CaseView(
        case_id=case.case_id,
        txn_id=case.txn_id,
        status=case.status,
        transaction=_transaction_facts(package),
        evidence=package,
        recommendation=recommendation,
        explanation=explanation,
    )


def drill_down(session: Session, case_id: str, element_id: str) -> DrillDownResponse:
    """Return the raw signal(s) behind one summarised evidence indicator (FR-15)."""
    case = session.get(CaseModel, case_id)
    if case is None:
        raise CaseNotFound(f"case not found: {case_id}", {"case_id": case_id})
    package = EvidencePackage.model_validate(case.evidence)
    for element in package.elements:
        if element.element_id == element_id:
            return DrillDownResponse(
                case_id=case_id,
                element_id=element.element_id,
                label=element.label,
                source=element.source,
                raw=element.raw,
            )
    raise ElementNotFound(f"element not found: {element_id}", {"element_id": element_id})
