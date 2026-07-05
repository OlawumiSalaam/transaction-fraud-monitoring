"""Queue service: the prioritised, re-sortable, filterable triage queue (FR-14, FR-19).

Ordering is an operational policy (config), visible and re-sortable — not a property
of a model score. With the scorer excluded, "risk" priority is derived from the
deterministic recommendation severity. Filtering is applied in memory (the demo
queue is small); this is a presentation/orchestration concern, no new fraud logic.

Spec references: FR-14, FR-19; Addendum §2.3.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from tfm.api.schemas import QueueItem, QueueResponse
from tfm.config.settings import AppConfig
from tfm.persistence.models import Case as CaseModel

_OPEN_STATUSES = ("queued", "pending")
_SEVERITY = {"escalate": 2, "hold": 1, "clear": 0}


def _amount_and_type(case: CaseModel) -> tuple[float, str]:
    by_id = {e["element_id"]: e for e in case.evidence.get("elements", [])}
    facts = by_id.get("txn_facts", {}).get("raw", {})
    return float(facts.get("amount", 0.0)), str(facts.get("type", ""))


def _rule_ids(case: CaseModel) -> tuple[str, ...]:
    return tuple(case.recommendation_basis.get("rule_ids", []))


def list_queue(
    session: Session,
    config: AppConfig,
    *,
    sort: str | None = None,
    level: str | None = None,
    rule: str | None = None,
    min_amount: float | None = None,
) -> QueueResponse:
    """Return open cases, filtered and ordered by the (visible) configured basis."""
    allowed = config.queue_policy.allowed_sorts
    sort_by = sort if sort in allowed else config.queue_policy.default_sort
    order = config.queue_policy.order
    reverse = order == "desc"

    cases = session.scalars(select(CaseModel).where(CaseModel.status.in_(_OPEN_STATUSES))).all()

    items: list[QueueItem] = []
    for case in cases:
        amount, txn_type = _amount_and_type(case)
        rule_ids = _rule_ids(case)
        if level is not None and case.recommendation_action != level:
            continue
        if rule is not None and rule not in rule_ids:
            continue
        if min_amount is not None and amount < min_amount:
            continue
        items.append(
            QueueItem(
                case_id=case.case_id,
                txn_id=case.txn_id,
                action=case.recommendation_action,
                confidence=case.recommendation_confidence,
                amount=amount,
                type=txn_type,
                rule_ids=rule_ids,
                uncertainty_flag=case.uncertainty_flag,
                created_at=case.created_at,
            )
        )

    if sort_by == "case_age":
        items.sort(key=lambda i: i.created_at, reverse=reverse)
    else:  # "risk" — deterministic recommendation severity, then recency
        items.sort(key=lambda i: (_SEVERITY.get(i.action, 0), i.created_at), reverse=reverse)

    filters: dict[str, str] = {}
    if level is not None:
        filters["level"] = level
    if rule is not None:
        filters["rule"] = rule
    if min_amount is not None:
        filters["min_amount"] = str(min_amount)

    return QueueResponse(
        ordering_basis=sort_by, order=order, filters_applied=filters, items=tuple(items)
    )
