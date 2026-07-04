"""Evidence Assembler: builds the Case evidence package, defines the groundable set (FR-2).

Contract (Addendum §4 — Evidence Assembler):
  In:  transaction + account history + counterparty + score(-status) + rule hits.
  Out: the assembled EvidencePackage answering the seven evidence requirements
       (§265), plus the explicit groundable evidence set.

Architectural responsibility: the assembler *assembles* — it does not score,
recommend, explain, rank, or decide (Layer Separation). Every emitted element
traces to a canonical field, a rule hit, or a score signal (total traceability
invariant). The recommendation (M5) and explanation (M6) are populated downstream.

The seven evidence requirements (§265) and their sources:
  1. What happened            → transaction facts (amount, timestamp, type, origin, counterparty)
  2. Why flagged (human terms)→ interpretable feature fields + rule hits
  3. Abnormal for this account→ the account's prior history (or an explicit no-baseline element)
  4. Broader pattern          → counterparty linkage
  5. Direction + balances     → direction and both-side balances
  6. Risk score               → the score, or its honest FR-4 exclusion
  7. Synthetic-data disclosure→ display-only disclosure (never grounded)

Honest degradation:
  - Ineligible scorer (FR-4): requirement 6 is a populated ``score_signal`` element
    carrying the exclusion reason but no probability — so no score value traces to
    any element and a score claim is structurally ungroundable.
  - First-observed account: requirement 3 is an explicit no-baseline element whose
    stated reason is itself groundable.

Groundable classification (documented, tested):
  - Groundable (M6 may cite): transaction facts, direction+balances, interpretable
    features, account history / no-baseline (incl. reason), counterparty, rule hits,
    and the score signal (incl. the exclusion reason).
  - Display-only (not groundable): the synthetic-data disclosure — shown to the
    analyst (FR-13) but not an evidentiary claim about the transaction's risk.

Spec references: FR-2, FR-13; §6.2, §6.4, §6.7, §265; Addendum §4.
"""

from __future__ import annotations

from collections.abc import Sequence

from tfm.schema.entities import Counterparty, Transaction
from tfm.schema.evidence import (
    EvidenceElement,
    EvidencePackage,
    EvidenceScalar,
    FeatureVector,
    RuleHit,
    ScoreStatus,
)

# Requirement 7 (§6.4, §6.7): no real or identifiable customer data is present.
SYNTHETIC_DATA_DISCLOSURE = (
    "All data is synthetic (PaySim mobile-money simulator); no real or identifiable "
    "customer information is present. Results are measured on synthetic data."
)

NO_BASELINE_REASON = "first observed transaction; no behavioural baseline available"


def _element(
    element_id: str,
    label: str,
    source: str,
    raw: dict[str, EvidenceScalar],
    *,
    groundable: bool,
    requirements: tuple[int, ...],
) -> EvidenceElement:
    return EvidenceElement(
        element_id=element_id,
        label=label,
        source=source,  # type: ignore[arg-type]
        raw=raw,
        groundable=groundable,
        requirements=requirements,
    )


def _transaction_facts(txn: Transaction) -> EvidenceElement:
    """Requirement 1 — what happened."""
    return _element(
        "txn_facts",
        "Transaction facts",
        "transaction",
        {
            "txn_id": txn.txn_id,
            "event_ts": txn.event_ts.isoformat(),
            "type": str(txn.type),
            "amount": txn.amount,
            "account_id": txn.account_id,
            "counterparty_id": txn.counterparty_id,
        },
        groundable=True,
        requirements=(1,),
    )


def _direction_and_balances(txn: Transaction) -> EvidenceElement:
    """Requirement 5 — direction and both-side balances (mule / rapid-movement signal)."""
    return _element(
        "direction_balances",
        "Direction and balances",
        "transaction",
        {
            "direction": txn.direction,
            "bal_orig_before": txn.bal_orig_before,
            "bal_orig_after": txn.bal_orig_after,
            "bal_dest_before": txn.bal_dest_before,
            "bal_dest_after": txn.bal_dest_after,
        },
        groundable=True,
        requirements=(5,),
    )


def _interpretable_features(features: FeatureVector) -> EvidenceElement:
    """Requirement 2 — the human-readable derived fields behind the flag."""
    return _element(
        "interpretable_features",
        "Interpretable features",
        "transaction",
        {
            "frac_bal_orig_moved": features.frac_bal_orig_moved,
            "orig_account_emptied": features.orig_account_emptied,
            "is_new_counterparty": features.is_new_counterparty,
        },
        groundable=True,
        requirements=(2,),
    )


def _account_history(features: FeatureVector, prior_transaction_count: int) -> EvidenceElement:
    """Requirement 3 — abnormal for this account, or an explicit no-baseline element."""
    if prior_transaction_count <= 0:
        return _element(
            "account_baseline",
            "No behavioural baseline",
            "account_history",
            {"prior_transaction_count": 0, "reason": NO_BASELINE_REASON},
            groundable=True,
            requirements=(3,),
        )
    return _element(
        "account_baseline",
        "Account behavioural history",
        "account_history",
        {
            "prior_transaction_count": prior_transaction_count,
            "txn_count_24h": features.txn_count_24h,
            "amount_sum_24h": features.amount_sum_24h,
            "distinct_counterparties_seen": features.distinct_counterparties_seen,
        },
        groundable=True,
        requirements=(3,),
    )


def _counterparty(counterparty: Counterparty, features: FeatureVector) -> EvidenceElement:
    """Requirement 4 — counterparty linkage (broader pattern)."""
    return _element(
        "counterparty",
        "Counterparty linkage",
        "counterparty",
        {
            "counterparty_id": counterparty.counterparty_id,
            "is_merchant": counterparty.is_merchant,
            "is_new_counterparty": features.is_new_counterparty,
        },
        groundable=True,
        requirements=(4,),
    )


def _rule_element(hit: RuleHit) -> EvidenceElement:
    """Requirement 2 — a fired deterministic rule as auditable evidence."""
    raw: dict[str, EvidenceScalar] = {"rule_id": hit.rule_id, "summary": hit.summary}
    raw.update(hit.evidence)
    return _element(
        f"rule:{hit.rule_id}",
        hit.summary,
        "rule",
        raw,
        groundable=True,
        requirements=(2,),
    )


def _score_signal(score: ScoreStatus) -> EvidenceElement:
    """Requirement 6 — the risk score, or its honest FR-4 exclusion.

    When excluded, the raw payload carries the reason but NO probability, so no score
    value traces to any element (a score claim is structurally ungroundable).
    """
    if score.available:
        return _element(
            "score_signal",
            "Risk score",
            "score_signal",
            {
                "status": "available",
                "model_version_id": score.model_version_id,
                "probability": score.probability,
                "calibrated": score.calibrated,
            },
            groundable=True,
            requirements=(6,),
        )
    return _element(
        "score_signal",
        "Operational score excluded (FR-4)",
        "score_signal",
        {
            "status": "excluded",
            "model_version_id": score.model_version_id,
            "leakage_verdict": score.leakage_verdict,
            "excluded_under": "FR-4",
            "reason": score.exclusion_reason
            or "model excluded from operational scoring under FR-4",
        },
        groundable=True,
        requirements=(6,),
    )


def _disclosure() -> EvidenceElement:
    """Requirement 7 — synthetic-data disclosure (display-only; never grounded)."""
    return _element(
        "disclosure:synthetic_data",
        "Synthetic data disclosure",
        "disclosure",
        {"synthetic_data": SYNTHETIC_DATA_DISCLOSURE},
        groundable=False,
        requirements=(7,),
    )


def assemble_evidence(
    *,
    transaction: Transaction,
    features: FeatureVector,
    prior_transaction_count: int,
    counterparty: Counterparty,
    score: ScoreStatus,
    rule_hits: Sequence[RuleHit],
) -> EvidencePackage:
    """Assemble the evidence package for one flagged transaction (FR-2, push).

    Pure function of its domain inputs — no I/O, no mutation. The caller (the
    ingest/pipeline service) supplies the point-in-time inputs; this function pushes
    a complete evidence package answering all seven requirements, with the groundable
    set defined by element ``groundable`` flags.
    """
    elements: list[EvidenceElement] = [
        _transaction_facts(transaction),
        _interpretable_features(features),
        *(_rule_element(hit) for hit in rule_hits),
        _account_history(features, prior_transaction_count),
        _counterparty(counterparty, features),
        _direction_and_balances(transaction),
        _score_signal(score),
        _disclosure(),
    ]
    return EvidencePackage(txn_id=transaction.txn_id, elements=tuple(elements))
