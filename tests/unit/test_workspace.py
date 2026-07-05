"""Unit tests for the M7 service layer + presentation helpers.

Covers case assembly/composition, queue ordering + filtering, the disposition
engagement floor / rationale graduation / routing / **complete audit snapshot**,
and the analyst-facing render helpers (incl. the no-default disposition control).

Spec: FR-14, FR-15, FR-16, FR-17, FR-18, FR-19, FR-20; Addendum §2.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from tfm.audit.log import AuditWriter
from tfm.audit.snapshot import SNAPSHOT_VERSION
from tfm.config.settings import Settings, load_config
from tfm.persistence.models import AuditLog
from tfm.schema.entities import Counterparty, Transaction, TransactionType
from tfm.schema.evidence import FeatureVector, ScoreStatus
from tfm.services import case_service, disposition_service, queue_service
from tfm.services.errors import (
    CaseAlreadyDispositioned,
    CaseNotFound,
    RationaleFloorRequired,
    RationaleRequiredForAction,
)
from tfm.web import render

_CONFIG = load_config(Settings(config_dir="config"))


def _excluded() -> ScoreStatus:
    return ScoreStatus(
        available=False,
        model_version_id="tfm-scorer-20260704053632",
        leakage_verdict="fail",
        exclusion_reason="excluded under FR-4",
    )


def _txn(
    txn_id: str = "t1",
    account: str = "C1",
    cp: str = "C900",
    amount: float = 441423.0,
    drained: bool = True,
) -> Transaction:
    return Transaction(
        txn_id=txn_id,
        step=3,
        event_ts=datetime(2024, 1, 9, 20, tzinfo=UTC),
        type=TransactionType.TRANSFER,
        amount=amount,
        account_id=account,
        counterparty_id=cp,
        direction="outbound",
        bal_orig_before=amount,
        bal_orig_after=0.0 if drained else amount,
        bal_dest_before=0.0,
        bal_dest_after=amount,
        sim_flagged=False,
        label=True,
    )


def _features(txn: Transaction, drained: bool = True) -> FeatureVector:
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
        bal_orig_after=0.0 if drained else txn.amount,
        bal_dest_before=0.0,
        bal_dest_after=txn.amount,
        frac_bal_orig_moved=1.0 if drained else 0.05,
        orig_account_emptied=drained,
        txn_count_24h=0,
        amount_sum_24h=0.0,
        is_new_counterparty=True,
        distinct_counterparties_seen=0,
    )


def _seed(session: Session, txn: Transaction) -> str:
    drained = txn.bal_orig_after == 0.0
    case = case_service.assemble_and_persist_case(
        session,
        transaction=txn,
        features=_features(txn, drained),
        prior_transaction_count=0,
        counterparty=Counterparty(counterparty_id=txn.counterparty_id, is_merchant=False),
        score=_excluded(),
        config=_CONFIG,
    )
    return case.case_id


# ── Case service: composition + drill-down ────────────────────────────────────


def test_case_view_composes_four_sections(session: Session) -> None:
    case_id = _seed(session, _txn())
    view = case_service.get_case_view(session, case_id)
    assert view.transaction.amount == 441423.0
    assert view.evidence.groundable_elements  # M4 object embedded
    assert view.recommendation.action == "escalate"  # M5 object
    assert view.explanation.pathway == "templated"  # M6 object
    assert view.disposition_options == ("clear", "hold", "escalate")


def test_drill_down_returns_raw_signal(session: Session) -> None:
    case_id = _seed(session, _txn())
    dd = case_service.drill_down(session, case_id, "rule:account_draining")
    assert dd.source == "rule"
    assert dd.raw["frac_bal_orig_moved"] == 1.0


def test_unknown_case_raises_not_found(session: Session) -> None:
    with pytest.raises(CaseNotFound):
        case_service.get_case_view(session, "nope")


# ── Queue service: ordering + filtering ───────────────────────────────────────


def test_queue_orders_escalate_before_hold(session: Session) -> None:
    _seed(session, _txn("t_hold", account="C2", amount=120.0, drained=False))  # -> hold
    _seed(session, _txn("t_esc", account="C3", amount=500000.0, drained=True))  # -> escalate
    q = queue_service.list_queue(session, _CONFIG, sort="risk")
    assert q.ordering_basis == "risk"
    assert q.items[0].action == "escalate"


def test_queue_filters(session: Session) -> None:
    _seed(session, _txn("t_hold", account="C2", amount=120.0, drained=False))
    _seed(session, _txn("t_esc", account="C3", amount=500000.0, drained=True))
    only_esc = queue_service.list_queue(session, _CONFIG, level="escalate")
    assert [i.action for i in only_esc.items] == ["escalate"]
    by_rule = queue_service.list_queue(session, _CONFIG, rule="account_draining")
    assert all("account_draining" in i.rule_ids for i in by_rule.items)
    by_amount = queue_service.list_queue(session, _CONFIG, min_amount=1000.0)
    assert all(i.amount >= 1000.0 for i in by_amount.items)


# ── Disposition service: floor, graduation, routing, audit, no auto-execution ──


def test_engagement_floor_requires_reason_code(session: Session) -> None:
    case_id = _seed(session, _txn())
    with pytest.raises(RationaleFloorRequired):
        disposition_service.record_disposition(
            session,
            _CONFIG,
            AuditWriter(),
            case_id=case_id,
            action="clear",
            reason_code="  ",
            rationale=None,
            follow_up=None,
            analyst_id="a",
        )


def test_escalate_requires_rationale(session: Session) -> None:
    case_id = _seed(session, _txn())
    with pytest.raises(RationaleRequiredForAction):
        disposition_service.record_disposition(
            session,
            _CONFIG,
            AuditWriter(),
            case_id=case_id,
            action="escalate",
            reason_code="likely_fraud",
            rationale=None,
            follow_up=None,
            analyst_id="a",
        )


def test_deviation_requires_rationale(session: Session) -> None:
    case_id = _seed(session, _txn())  # recommended escalate
    with pytest.raises(RationaleRequiredForAction):  # clear deviates -> rationale required
        disposition_service.record_disposition(
            session,
            _CONFIG,
            AuditWriter(),
            case_id=case_id,
            action="clear",
            reason_code="legitimate",
            rationale=None,
            follow_up=None,
            analyst_id="a",
        )


def test_disposition_routes_and_is_not_auto_executed(session: Session) -> None:
    case_id = _seed(session, _txn())
    resp = disposition_service.record_disposition(
        session,
        _CONFIG,
        AuditWriter(),
        case_id=case_id,
        action="escalate",
        reason_code="likely_fraud",
        rationale="clear draining pattern",
        follow_up=None,
        analyst_id="ana",
    )
    assert resp.status == "escalated"
    assert resp.deviated_from_recommendation is False
    view = case_service.get_case_view(session, case_id)
    assert view.status == "escalated"  # routing = state change only


def test_double_disposition_conflicts(session: Session) -> None:
    case_id = _seed(session, _txn())
    disposition_service.record_disposition(
        session,
        _CONFIG,
        AuditWriter(),
        case_id=case_id,
        action="escalate",
        reason_code="likely_fraud",
        rationale="x",
        follow_up=None,
        analyst_id="a",
    )
    with pytest.raises(CaseAlreadyDispositioned):
        disposition_service.record_disposition(
            session,
            _CONFIG,
            AuditWriter(),
            case_id=case_id,
            action="hold",
            reason_code="needs_review",
            rationale=None,
            follow_up=None,
            analyst_id="a",
        )


def test_disposition_audit_snapshot_is_complete(session: Session) -> None:
    case_id = _seed(session, _txn())
    disposition_service.record_disposition(
        session,
        _CONFIG,
        AuditWriter(),
        case_id=case_id,
        action="escalate",
        reason_code="likely_fraud",
        rationale="draining",
        follow_up=None,
        analyst_id="analyst-7",
    )
    record = session.scalars(select(AuditLog).where(AuditLog.case_id == case_id)).one()
    p = record.payload
    assert record.event_type == "disposition_recorded"
    assert p["snapshot_version"] == SNAPSHOT_VERSION
    for key in (
        "case_id",
        "txn_id",
        "analyst_id",
        "recorded_at",
        "evidence",
        "recommendation",
        "explanation",
        "disposition",
        "routing",
        "provenance",
    ):
        assert key in p, f"decision snapshot missing {key}"
    # Explanation completeness — the M8 gap closed: text + grounding, not just pathway.
    assert p["explanation"]["text"]
    assert p["explanation"]["pathway"] == "templated"
    assert "grounding" in p["explanation"]
    # Routing state captured (reproducible without the operational cases table).
    assert p["routing"]["status"] == "escalated"
    assert p["routing"]["routed_to"] == "escalation"
    for key in ("action", "reason_code", "rationale", "deviated_from_recommendation", "follow_up"):
        assert key in p["disposition"], f"disposition snapshot missing {key}"
    assert p["analyst_id"] == "analyst-7"
    assert p["provenance"]["score_available"] is False  # FR-4 excluded: no fabricated score


# ── Render helpers (analyst language + no-default disposition) ─────────────────


def test_render_risk_indicators_use_analyst_language(session: Session) -> None:
    case_id = _seed(session, _txn())
    view = case_service.get_case_view(session, case_id).model_dump()
    labels = [i["label"] for i in render.risk_indicators(view)]
    assert "Account draining detected" in labels
    assert "First observed account" in labels


def test_render_decision_basis_note_reads_as_governance(session: Session) -> None:
    case_id = _seed(session, _txn())
    view = case_service.get_case_view(session, case_id).model_dump()
    note = render.decision_basis_note(view)
    assert "excluded by the leakage gate" in note
    assert "verified rule evidence" in note


def test_render_disposition_control_has_no_default() -> None:
    control = render.disposition_control(("clear", "hold", "escalate"))
    assert control["index"] is None  # renders unselected


def test_render_rationale_required() -> None:
    assert render.rationale_required("escalate", "hold") is True
    assert render.rationale_required("clear", "escalate") is True  # deviation
    assert render.rationale_required("hold", "hold") is False
