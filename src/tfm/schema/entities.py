"""Canonical entities: Transaction, Account, Counterparty, derived profiles.

Implements the Canonical Evidence Schema as immutable Pydantic domain
types. Every component — the data pipeline, feature engineering, rule engine,
ML scorer, grounding layer, case view, and audit log — operates on these types
(Architectural Principle: Canonical Evidence Schema).
Architectural responsibility: the spine. Every layer imports from schema/,
never from a private shape.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class TransactionType(StrEnum):
    """PaySim transaction types.

    Fraud occurs only in TRANSFER and CASH_OUT in the PaySim dataset.
    Interpretable type fields are required by the rule engine and the LLM
    grounding layer.
    """

    PAYMENT = "PAYMENT"
    TRANSFER = "TRANSFER"
    CASH_OUT = "CASH_OUT"
    CASH_IN = "CASH_IN"
    DEBIT = "DEBIT"


class Transaction(BaseModel):
    """Core event: a single financial transaction in the canonical schema.

    All discriminating fields are preserved (no dropping): direction, both-side
    balances, and counterparty are load-bearing for mule and rapid-movement
    detection.

    sim_flagged (PaySim isFlaggedFraud) is stored for provenance only — it is
    excluded from every feature computation to prevent trivial simulator leakage.
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

    sim_flagged: bool  # ingested for provenance; NEVER used as a feature
    label: bool


class Account(BaseModel):
    """The entity whose behaviour is judged; a stable id to gather history."""

    model_config = ConfigDict(frozen=True)

    account_id: str
    first_seen_step: int | None
    # PaySim: merchant destinations ('M' prefix) carry no balance signal.
    is_merchant: bool


class Counterparty(BaseModel):
    """The other side of a transaction — peer account or merchant."""

    model_config = ConfigDict(frozen=True)

    counterparty_id: str
    is_merchant: bool


class AccountBehaviouralProfile(BaseModel):
    """Derived: aggregates over an account's own transaction history.

    Computed point-in-time — only transactions with event_ts
    strictly earlier than the reference transaction's event_ts are included.
    Not a source table; produced by the Feature Builder (data/features.py).
    """

    model_config = ConfigDict(frozen=True)

    account_id: str
    reference_txn_id: str

    # 24-hour trailing window signals (point-in-time)
    txn_count_24h: int
    amount_sum_24h: float
    distinct_counterparties_seen: int


class BeneficiaryRelationship(BaseModel):
    """Derived: whether the counterparty is new to this account.

    Computed point-in-time. Supports the new-beneficiary rule
    and the new_beneficiary_large rule definition.
    """

    model_config = ConfigDict(frozen=True)

    account_id: str
    counterparty_id: str
    reference_txn_id: str

    # True if this is the first recorded transaction from this account to this counterparty.
    is_new_counterparty: bool
    prior_txn_count: int
