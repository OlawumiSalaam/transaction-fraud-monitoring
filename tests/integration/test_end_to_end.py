"""End-to-end integration: the whole system working together (M10).

Exercises the online loop over the real FastAPI app with the **LLM disabled** (the
default) — proving graceful degradation (templated + grounded explanation), the full
analyst workflow (queue → case → disposition → route → audit), and reconstruction
from the audit log — all on one composed stack. No product logic is added here; this
verifies the already-built layers integrate.

Spec: NFR-2 (graceful degradation), NFR-3 (reconstructability), the acceptance loop.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from tfm.api.app import configure_app
from tfm.api.deps import get_audit_writer, get_config, get_session, get_settings
from tfm.audit.log import AuditWriter
from tfm.audit.reconstruct import reconstruct_decision
from tfm.config.settings import Settings, load_config
from tfm.persistence.models import Base
from tfm.schema.entities import Counterparty, Transaction, TransactionType
from tfm.schema.evidence import FeatureVector, ScoreStatus
from tfm.services import case_service

_EXCLUDED = ScoreStatus(
    available=False,
    model_version_id="tfm-scorer-20260704053632",
    leakage_verdict="fail",
    exclusion_reason="excluded under FR-4",
)


def _draining_case(session: Session, config: object) -> str:
    txn = Transaction(
        txn_id="e2e-drain",
        step=3,
        event_ts=datetime(2024, 1, 9, 20, tzinfo=UTC),
        type=TransactionType.TRANSFER,
        amount=441423.0,
        account_id="A1",
        counterparty_id="B9",
        direction="outbound",
        bal_orig_before=441423.0,
        bal_orig_after=0.0,
        bal_dest_before=0.0,
        bal_dest_after=441423.0,
        sim_flagged=False,
        label=True,
    )
    features = FeatureVector(
        txn_id=txn.txn_id,
        account_id="A1",
        counterparty_id="B9",
        amount=441423.0,
        type_payment=False,
        type_transfer=True,
        type_cash_out=False,
        type_cash_in=False,
        type_debit=False,
        bal_orig_before=441423.0,
        bal_orig_after=0.0,
        bal_dest_before=0.0,
        bal_dest_after=441423.0,
        frac_bal_orig_moved=1.0,
        orig_account_emptied=True,
        txn_count_24h=0,
        amount_sum_24h=0.0,
        is_new_counterparty=True,
        distinct_counterparties_seen=0,
    )
    case = case_service.assemble_and_persist_case(
        session,
        transaction=txn,
        features=features,
        prior_transaction_count=0,
        counterparty=Counterparty(counterparty_id="B9", is_merchant=False),
        score=_EXCLUDED,
        config=config,
        llm_enabled=False,
    )
    return case.case_id


@pytest.fixture
def stack() -> Iterator[tuple[TestClient, sessionmaker[Session], str]]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    settings = Settings(
        config_dir="config", app_env="ci", database_url="sqlite://", llm_enabled=False
    )
    config = load_config(settings)
    writer = AuditWriter()

    with factory() as seed:
        case_id = _draining_case(seed, config)
        seed.commit()

    def _override_session() -> Iterator[Session]:
        s = factory()
        try:
            yield s
            s.commit()
        finally:
            s.close()

    app = FastAPI()
    configure_app(app)
    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_config] = lambda: config
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_audit_writer] = lambda: writer

    with TestClient(app) as client:
        yield client, factory, case_id
    engine.dispose()


def test_full_workflow_with_llm_disabled(
    stack: tuple[TestClient, sessionmaker[Session], str],
) -> None:
    client, factory, case_id = stack

    # Triage queue populated, escalate surfaced.
    queue = client.get("/api/queue").json()
    assert queue["items"] and queue["items"][0]["action"] == "escalate"

    # Case view: graceful degradation — templated pathway, and still grounded.
    case = client.get(f"/api/cases/{case_id}").json()
    assert case["explanation"]["pathway"] == "templated"  # LLM disabled -> templated floor
    assert case["explanation"]["ai_generated"] is True
    assert case["explanation"]["grounding"]["verified"] is True  # grounded explanation
    assert case["recommendation"]["action"] == "escalate"
    assert case["recommendation"]["basis"]["score_band"] == "none"  # honest FR-4 exclusion

    # Drill-down to the raw signal behind a risk indicator.
    dd = client.get(f"/api/cases/{case_id}/evidence/rule:account_draining").json()
    assert dd["raw"]["frac_bal_orig_moved"] == 1.0

    # Record the disposition; route as a state change.
    resp = client.post(
        f"/api/cases/{case_id}/disposition",
        json={"action": "escalate", "reason_code": "likely_fraud", "rationale": "clear drain"},
        headers={"X-Analyst-Id": "e2e"},
    )
    assert resp.status_code == 200 and resp.json()["status"] == "escalated"

    # Audit written and the case has left the open queue.
    audit = client.get(f"/api/cases/{case_id}/audit").json()
    assert audit and audit[0]["event_type"] == "disposition_recorded"
    assert client.get("/api/queue").json()["items"] == []

    # Reconstruct the decision from the audit log alone (NFR-3), still templated + grounded.
    with factory() as session:
        decision = reconstruct_decision(session, case_id)
    assert decision.recommendation.action == "escalate"
    assert decision.explanation.pathway == "templated"
    assert decision.explanation.grounding.verified is True
    assert decision.disposition.action == "escalate"
    assert decision.routing.status == "escalated"
