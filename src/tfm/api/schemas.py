"""API request/response schemas for the analyst workspace.

These compose the domain objects for the case view — they never
duplicate or re-derive them. The presentation layer (``web/``) maps these into
analyst language; the API returns the composed, bounded objects.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from tfm.explanation.explainer import Explanation
from tfm.recommendation.policy import Recommendation
from tfm.schema.evidence import EvidencePackage


class TransactionFacts(BaseModel):
    """What happened — the canonical transaction facts section."""

    model_config = ConfigDict(frozen=True)

    txn_id: str
    amount: float
    type: str
    event_ts: str
    account_id: str
    counterparty_id: str
    direction: str


class QueueItem(BaseModel):
    """One row of the triage queue."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    txn_id: str
    action: str  # recommended action (advisory)
    confidence: str
    amount: float
    type: str
    rule_ids: tuple[str, ...]
    uncertainty_flag: bool
    created_at: datetime


class QueueResponse(BaseModel):
    """The queue plus its visible ordering basis and applied filters."""

    model_config = ConfigDict(frozen=True)

    ordering_basis: str  # e.g. "risk" | "case_age"
    order: str  # "asc" | "desc"
    filters_applied: dict[str, str]
    items: tuple[QueueItem, ...]


class CaseView(BaseModel):
    """The complete case presented to the analyst — composed, boundaries preserved.

    ``evidence`` / ``recommendation`` / ``explanation`` are the objects
    embedded verbatim; ``disposition_options`` carry no default selection.
    """

    model_config = ConfigDict(frozen=True)

    case_id: str
    txn_id: str
    status: str
    transaction: TransactionFacts
    evidence: EvidencePackage
    recommendation: Recommendation
    explanation: Explanation
    disposition_options: tuple[str, ...] = ("clear", "hold", "escalate")


class DrillDownResponse(BaseModel):
    """The raw signal(s) behind one summarised evidence indicator."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    element_id: str
    label: str
    source: str
    raw: dict[str, float | int | bool | str | None]


class DispositionRequest(BaseModel):
    """The analyst's decision. The human is the sole decider."""

    model_config = ConfigDict(frozen=True)

    action: str  # clear | hold | escalate
    reason_code: str  # REQUIRED — engagement floor (architectural)
    rationale: str | None = None  # REQUIRED for escalate or a deviation
    follow_up: str | None = None  # hold only, optional


class DispositionResponse(BaseModel):
    """The recorded disposition + routing outcome."""

    model_config = ConfigDict(frozen=True)

    disposition_id: str
    case_id: str
    action: str
    deviated_from_recommendation: bool
    routed_to: str
    status: str  # cleared | pending | escalated
    recorded_at: datetime
