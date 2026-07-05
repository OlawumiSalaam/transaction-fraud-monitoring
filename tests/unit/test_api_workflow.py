"""API workflow tests for the analyst loop (M7).

Exercises the five routes end to end via a TestClient over a shared in-memory DB:
queue → case → drill-down → disposition → audit, plus the engagement-floor error
and the graceful-degradation contract (case returns 200 with the templated
explanation and the score-exclusion, never a 5xx).

Spec: FR-14, FR-15, FR-16, FR-17, FR-20; Addendum §2.3, §2.5.
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
from tfm.config.settings import Settings, load_config
from tfm.persistence.models import Base
from tfm.schema.entities import Counterparty, Transaction, TransactionType
from tfm.schema.evidence import FeatureVector, ScoreStatus
from tfm.services import case_service


def _seed_case(session: Session) -> str:
    txn = Transaction(
        txn_id="demo-0000",
        step=3,
        event_ts=datetime(2024, 1, 9, 20, tzinfo=UTC),
        type=TransactionType.TRANSFER,
        amount=441423.0,
        account_id="C1231006815",
        counterparty_id="C1900112025",
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
        account_id=txn.account_id,
        counterparty_id=txn.counterparty_id,
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
    score = ScoreStatus(
        available=False,
        model_version_id="tfm-scorer-x",
        leakage_verdict="fail",
        exclusion_reason="excluded under FR-4",
    )
    case = case_service.assemble_and_persist_case(
        session,
        transaction=txn,
        features=features,
        prior_transaction_count=0,
        counterparty=Counterparty(counterparty_id=txn.counterparty_id, is_merchant=False),
        score=score,
        config=load_config(Settings(config_dir="config")),
    )
    return case.case_id


@pytest.fixture
def client_and_case() -> Iterator[tuple[TestClient, str]]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    settings = Settings(config_dir="config", app_env="ci", database_url="sqlite://")
    config = load_config(settings)
    writer = AuditWriter()

    with factory() as seed_session:
        case_id = _seed_case(seed_session)
        seed_session.commit()

    def _override_session() -> Iterator[Session]:
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app = FastAPI()
    configure_app(app)
    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_config] = lambda: config
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_audit_writer] = lambda: writer

    with TestClient(app) as client:
        yield client, case_id
    engine.dispose()


def test_queue_returns_open_cases(client_and_case: tuple[TestClient, str]) -> None:
    client, _ = client_and_case
    resp = client.get("/api/queue")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ordering_basis"] == "risk"
    assert len(body["items"]) == 1
    assert body["items"][0]["action"] == "escalate"


def test_case_view_composed_and_degrades_gracefully(
    client_and_case: tuple[TestClient, str],
) -> None:
    client, case_id = client_and_case
    resp = client.get(f"/api/cases/{case_id}")
    assert resp.status_code == 200  # never 5xx for the excluded scorer
    body = resp.json()
    assert body["transaction"]["amount"] == 441423.0
    assert body["recommendation"]["action"] == "escalate"
    assert body["recommendation"]["basis"]["score_band"] == "none"  # honest exclusion
    assert body["explanation"]["pathway"] == "templated"
    assert body["explanation"]["ai_generated"] is True
    assert body["disposition_options"] == ["clear", "hold", "escalate"]


def test_drill_down(client_and_case: tuple[TestClient, str]) -> None:
    client, case_id = client_and_case
    resp = client.get(f"/api/cases/{case_id}/evidence/rule:account_draining")
    assert resp.status_code == 200
    assert resp.json()["raw"]["frac_bal_orig_moved"] == 1.0


def test_disposition_floor_violation(client_and_case: tuple[TestClient, str]) -> None:
    client, case_id = client_and_case
    resp = client.post(
        f"/api/cases/{case_id}/disposition",
        json={"action": "clear", "reason_code": "", "rationale": None},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "RATIONALE_FLOOR_REQUIRED"


def test_full_disposition_and_audit(client_and_case: tuple[TestClient, str]) -> None:
    client, case_id = client_and_case
    resp = client.post(
        f"/api/cases/{case_id}/disposition",
        json={"action": "escalate", "reason_code": "likely_fraud", "rationale": "draining pattern"},
        headers={"X-Analyst-Id": "judge-demo"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "escalated"

    audit = client.get(f"/api/cases/{case_id}/audit").json()
    assert len(audit) == 1
    assert audit[0]["event_type"] == "disposition_recorded"
    assert audit[0]["payload"]["analyst_id"] == "judge-demo"
    assert "evidence" in audit[0]["payload"]  # full EvidencePackage snapshot (M8)

    # Case has left the open queue.
    assert len(client.get("/api/queue").json()["items"]) == 0
