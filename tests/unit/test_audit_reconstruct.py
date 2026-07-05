"""Reconstructability tests (M8, NFR-3).

Proves a decision is fully reconstructable from the single ``disposition_recorded``
audit event alone, and that reconstruction is **pure deserialization** — it invokes
no rule engine, recommendation policy, explanation generation, grounding, or
configuration, and reads no operational table.

Spec: FR-20, NFR-3; Release Plan §M8 (single-event boundary).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from tfm.audit.log import AuditWriter
from tfm.audit.reconstruct import DecisionNotReconstructable, reconstruct_decision
from tfm.audit.snapshot import DecisionSnapshot
from tfm.config.settings import Settings, load_config
from tfm.persistence.models import Case as CaseModel
from tfm.persistence.models import Disposition as DispositionModel
from tfm.persistence.models import RuleHit as RuleHitModel
from tfm.schema.entities import Counterparty, Transaction, TransactionType
from tfm.schema.evidence import FeatureVector, ScoreStatus
from tfm.services import case_service, disposition_service

_CONFIG = load_config(Settings(config_dir="config"))
_WRITER = AuditWriter()


def _excluded() -> ScoreStatus:
    return ScoreStatus(
        available=False,
        model_version_id="tfm-scorer-20260704053632",
        leakage_verdict="fail",
        exclusion_reason="excluded under FR-4",
    )


def _txn() -> Transaction:
    return Transaction(
        txn_id="t1",
        step=3,
        event_ts=datetime(2024, 1, 9, 20, tzinfo=UTC),
        type=TransactionType.TRANSFER,
        amount=441423.0,
        account_id="C1",
        counterparty_id="C900",
        direction="outbound",
        bal_orig_before=441423.0,
        bal_orig_after=0.0,
        bal_dest_before=0.0,
        bal_dest_after=441423.0,
        sim_flagged=False,
        label=True,
    )


def _features(txn: Transaction) -> FeatureVector:
    return FeatureVector(
        txn_id=txn.txn_id,
        account_id=txn.account_id,
        counterparty_id=txn.counterparty_id,
        amount=txn.amount,
        type_payment=False,
        type_transfer=True,
        type_cash_out=False,
        type_cash_in=False,
        type_debit=False,
        bal_orig_before=txn.amount,
        bal_orig_after=0.0,
        bal_dest_before=0.0,
        bal_dest_after=txn.amount,
        frac_bal_orig_moved=1.0,
        orig_account_emptied=True,
        txn_count_24h=0,
        amount_sum_24h=0.0,
        is_new_counterparty=True,
        distinct_counterparties_seen=0,
    )


def _seed_and_dispose(session: Session) -> tuple[str, object]:
    """Assemble a case, capture the view the analyst saw, then record a disposition."""
    txn = _txn()
    case = case_service.assemble_and_persist_case(
        session,
        transaction=txn,
        features=_features(txn),
        prior_transaction_count=0,
        counterparty=Counterparty(counterparty_id=txn.counterparty_id, is_merchant=False),
        score=_excluded(),
        config=_CONFIG,
    )
    shown = case_service.get_case_view(session, case.case_id)  # what the analyst saw
    disposition_service.record_disposition(
        session,
        _CONFIG,
        _WRITER,
        case_id=case.case_id,
        action="escalate",
        reason_code="likely_fraud",
        rationale="Full-balance drain to a first-seen beneficiary.",
        follow_up=None,
        analyst_id="analyst-9",
    )
    return case.case_id, shown


# ── Snapshot integrity ────────────────────────────────────────────────────────


def test_snapshot_round_trips(session: Session) -> None:
    case_id, _ = _seed_and_dispose(session)
    rec = reconstruct_decision(session, case_id)
    # Re-serializing a validated snapshot equals the reconstructed objects (stable).
    again = DecisionSnapshot.model_validate(
        {
            "snapshot_version": rec.provenance.snapshot_version,
            "case_id": rec.case_id,
            "txn_id": rec.txn_id,
            "analyst_id": rec.analyst_id,
            "recorded_at": rec.recorded_at,
            "evidence": rec.evidence.model_dump(mode="json"),
            "recommendation": rec.recommendation.model_dump(mode="json"),
            "explanation": rec.explanation.model_dump(mode="json"),
            "disposition": rec.disposition.model_dump(mode="json"),
            "routing": rec.routing.model_dump(mode="json"),
            "provenance": rec.provenance.model_dump(mode="json"),
        }
    )
    assert again.evidence == rec.evidence
    assert again.explanation == rec.explanation


# ── The five reproduced objects equal exactly what was shown ──────────────────


def test_reconstruct_reproduces_the_five_objects(session: Session) -> None:
    case_id, shown = _seed_and_dispose(session)
    rec = reconstruct_decision(session, case_id)
    assert rec.evidence == shown.evidence  # EvidencePackage
    assert rec.recommendation == shown.recommendation  # Recommendation
    assert rec.explanation == shown.explanation  # Explanation (text + grounding)
    assert rec.disposition.action == "escalate"  # Disposition
    assert rec.disposition.reason_code == "likely_fraud"
    assert rec.routing.status == "escalated" and rec.routing.routed_to == "escalation"  # Routing


# ── Reconstructable from the audit log ALONE (no operational tables) ──────────


def test_reconstruct_without_operational_tables(session: Session) -> None:
    case_id, shown = _seed_and_dispose(session)
    # Wipe every operational table; keep only audit_log.
    session.execute(delete(DispositionModel))
    session.execute(delete(RuleHitModel))
    session.execute(delete(CaseModel))
    session.flush()
    rec = reconstruct_decision(session, case_id)  # audit_log is the sole source
    assert rec.evidence == shown.evidence
    assert rec.explanation.text == shown.explanation.text


# ── The load-bearing invariant: reconstruction runs NO decision logic ─────────


def test_reconstruct_invokes_no_decision_logic(session: Session, monkeypatch) -> None:
    case_id, shown = _seed_and_dispose(session)

    import tfm.config.settings as settings_mod
    import tfm.explanation.explainer as explainer_mod
    import tfm.explanation.grounding as grounding_mod
    import tfm.recommendation.policy as policy_mod
    import tfm.rules.engine as engine_mod

    def _boom(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("decision logic invoked during reconstruction")

    monkeypatch.setattr(engine_mod.RuleEngine, "evaluate", _boom)
    monkeypatch.setattr(policy_mod, "recommend", _boom)
    monkeypatch.setattr(explainer_mod, "explain", _boom)
    monkeypatch.setattr(grounding_mod.GroundingGate, "verify", _boom)
    monkeypatch.setattr(settings_mod, "load_config", _boom)

    rec = reconstruct_decision(session, case_id)  # must NOT raise — nothing recomputed
    assert rec.evidence == shown.evidence
    assert rec.recommendation == shown.recommendation
    assert rec.explanation == shown.explanation


# ── Immune to future change in the explanation template ───────────────────────


def test_reconstruct_is_immune_to_template_change(session: Session, monkeypatch) -> None:
    case_id, shown = _seed_and_dispose(session)
    original_text = shown.explanation.text

    import tfm.explanation.templated as templated_mod
    from tfm.explanation.explainer import Explanation, GroundingResult

    def _rewritten(self: object, package: object, recommendation: object) -> Explanation:
        return Explanation(
            text="REWRITTEN TEMPLATE OUTPUT",
            pathway="templated",
            grounding=GroundingResult(verified=True, groundable_fields_used=()),
        )

    monkeypatch.setattr(templated_mod.TemplatedExplainer, "explain", _rewritten)

    rec = reconstruct_decision(session, case_id)
    assert rec.explanation.text == original_text  # stored, not re-rendered
    assert "REWRITTEN" not in rec.explanation.text


# ── No disposition yet → not reconstructable ──────────────────────────────────


def test_reconstruct_requires_a_recorded_disposition(session: Session) -> None:
    txn = _txn()
    case = case_service.assemble_and_persist_case(
        session,
        transaction=txn,
        features=_features(txn),
        prior_transaction_count=0,
        counterparty=Counterparty(counterparty_id=txn.counterparty_id, is_merchant=False),
        score=_excluded(),
        config=_CONFIG,
    )
    with pytest.raises(DecisionNotReconstructable):
        reconstruct_decision(session, case.case_id)
