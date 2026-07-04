"""Canonical entities: Transaction, Account, Counterparty, derived profiles.

Implements the Canonical Evidence Schema (§6.2) as immutable Pydantic domain
types. Every component — the data pipeline, feature engineering, rule engine,
ML scorer, grounding layer, case view, and audit log — operates on these types
(Architectural Principle: Canonical Evidence Schema, §3).

Spec references: §6.2, §3, FR-1.
Architectural responsibility: the spine. Every layer imports from schema/,
never from a private shape.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class TransactionType(StrEnum):
    """PaySim transaction types (§6.3).

    Fraud occurs only in TRANSFER and CASH_OUT in the PaySim dataset (§6.4).
    Interpretable type fields are required by the rule engine and the LLM
    grounding layer (FR-6, §6.5).
    """

    PAYMENT = "PAYMENT"
    TRANSFER = "TRANSFER"
    CASH_OUT = "CASH_OUT"
    CASH_IN = "CASH_IN"
    DEBIT = "DEBIT"


class Transaction(BaseModel):
    """Core event: a single financial transaction in the canonical schema (§6.2).

    Spec: FR-1, §6.2, §6.3.
    All discriminating fields are preserved (no dropping): direction, both-side
    balances, and counterparty are load-bearing for mule and rapid-movement
    detection (C2, C4 in DDR-01; R1 guard in Addendum §5).

    sim_flagged (PaySim isFlaggedFraud) is stored for provenance only — it is
    excluded from every feature computation to prevent trivial simulator leakage
    (§6.5, §9, FR-26).
    """

    model_config = ConfigDict(frozen=True)

    txn_id: str
    step: int
    event_ts: datetime
    type: TransactionType
    amount: float

    account_id: str
    counterparty_id: str
    direction: str  # 'outbound' for all PaySim transactions (origin → destination)

    bal_orig_before: float | None
    bal_orig_after: float | None
    bal_dest_before: float | None  # None for merchant destinations (no balance signal)
    bal_dest_after: float | None  # None for merchant destinations

    sim_flagged: bool  # ingested for provenance; NEVER used as a feature (§6.5, §9)
    label: bool


class Account(BaseModel):
    """The entity whose behaviour is judged; a stable id to gather history (§6.2).

    Spec: §6.2, FR-1 (C1 — account linkage criterion in DDR-01).
    """

    model_config = ConfigDict(frozen=True)

    account_id: str
    first_seen_step: int | None
    # PaySim: merchant destinations ('M' prefix) carry no balance signal (R1).
    is_merchant: bool


class Counterparty(BaseModel):
    """The other side of a transaction — peer account or merchant (§6.2).

    Spec: §6.2, FR-1 (C2 — counterparty identification criterion in DDR-01).
    """

    model_config = ConfigDict(frozen=True)

    counterparty_id: str
    is_merchant: bool


class AccountBehaviouralProfile(BaseModel):
    """Derived: aggregates over an account's own transaction history (§6.2).

    Computed point-in-time (§6.5, §8.3) — only transactions with event_ts
    strictly earlier than the reference transaction's event_ts are included.
    Not a source table; produced by the Feature Builder (data/features.py).

    Spec: §6.2, §6.5, FR-1 (C5 — behavioural-history support).
    """

    model_config = ConfigDict(frozen=True)

    account_id: str
    reference_txn_id: str

    # 24-hour trailing window signals (point-in-time)
    txn_count_24h: int
    amount_sum_24h: float
    distinct_counterparties_seen: int


class BeneficiaryRelationship(BaseModel):
    """Derived: whether the counterparty is new to this account (§6.2).

    Computed point-in-time (§6.5). Supports the new-beneficiary rule (FR-6)
    and the new_beneficiary_large rule definition.

    Spec: §6.2, FR-6 (new_beneficiary_large rule input).
    """

    model_config = ConfigDict(frozen=True)

    account_id: str
    counterparty_id: str
    reference_txn_id: str

    # True if this is the first recorded transaction from this account to this counterparty.
    is_new_counterparty: bool
    prior_txn_count: int
