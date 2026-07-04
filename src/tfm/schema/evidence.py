"""Shared evidence schema: FeatureVector and RuleHit.

The assembled Case evidence record and groundable evidence set are completed
in M4. This module provides the shared spine those layers import:

- ``FeatureVector`` — the output of the Feature Builder (data/features.py),
  shared by the rule engine (M3) and the evidence assembler (M4). The ML scorer
  (M2) trains on the ``PRIMARY_FEATURE_COLUMNS`` subset (balance artifacts
  quarantined, IMP-011), not on the full vector verbatim.
- ``RuleHit`` — a deterministic rule firing, produced by the rule engine (M3)
  and consumed by the assembler (M4), recommendation policy (M5), and audit (M8).

A feature that is predictive but not interpretable is disqualified: the rule
engine and the LLM grounding layer require every field to be human-readable
(§6.5). sim_flagged is never present: it is ingested for provenance but
excluded from all features to prevent trivial simulator leakage (§6.5, §9).

Spec references: §3 (Canonical Evidence Schema principle), §6.5, FR-1, FR-5,
FR-6 (rule input/output fields).
Architectural responsibility: shared spine — scorer, rules, and assembler all
import these types, never a private feature or hit shape.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FeatureVector(BaseModel):
    """Point-in-time feature vector produced by the Feature Builder.

    The three consumers share this exact type:
    - Scorer (ML layer): uses numeric columns as input to the calibrated model.
    - Rule Engine (deterministic logic): reads named fields in auditable if-then
      rules (e.g., ``frac_bal_orig_moved`` for account-draining, ``is_new_counterparty``
      for new-beneficiary detection).
    - Evidence Assembler (M4): selects fields for the groundable evidence set
      so the LLM can reference only known, human-readable values.

    None values encode «not applicable» (e.g., ``bal_dest_before`` is None for
    merchant counterparties that carry no balance signal).  The ML scorer (M2)
    must impute or drop None/NaN fields before passing the matrix to sklearn.

    Spec: §6.5, FR-1, FR-5, FR-6.
    """

    model_config = ConfigDict(frozen=True)

    # ── Identifiers (not ML features) ─────────────────────────────────────────
    txn_id: str
    account_id: str
    counterparty_id: str

    # ── Transaction-intrinsic ─────────────────────────────────────────────────
    amount: float
    type_payment: bool
    type_transfer: bool
    type_cash_out: bool
    type_cash_in: bool
    type_debit: bool

    # ── Balance / sequence — both sides preserved (C4, §6.2) ─────────────────
    bal_orig_before: float
    bal_orig_after: float
    bal_dest_before: float | None  # None for merchant counterparties
    bal_dest_after: float | None  # None for merchant counterparties

    # Derived balance signals: load-bearing for account-draining (FR-6, §6.5)
    frac_bal_orig_moved: float | None  # amount / bal_orig_before; None if balance == 0
    orig_account_emptied: bool  # bal_orig_before > 0 and bal_orig_after == 0

    # ── Account-behavioural (24 h trailing window, point-in-time) ────────────
    txn_count_24h: int
    amount_sum_24h: float

    # ── Counterparty ─────────────────────────────────────────────────────────
    is_new_counterparty: bool
    distinct_counterparties_seen: int

    # ── Account-baseline deviation & sequence (point-in-time; §9, IMP-011) ────
    # None on an account's first transaction (no prior baseline). Defaulted to
    # None so the (always-None-on-first-txn) signals need not be restated at
    # every construction site; build_features' to_feature_vector always populates
    # them. amount_to_prior_max_ratio is a bounded engineering extension; the
    # other two directly implement §9 (deviation-from-baseline; sequence signal).
    amount_to_prior_mean_ratio: float | None = None  # amount / mean(prior amounts)
    amount_to_prior_max_ratio: float | None = None  # amount / max(prior amounts)
    hours_since_last_txn: float | None = None  # hours since the account's prior txn


class RuleHit(BaseModel):
    """A deterministic rule firing, preserved as auditable evidence (FR-6, FR-20).

    The rule engine (M3) produces these from the shared ``FeatureVector``. Each hit
    names the rule and carries the exact fields and thresholds that made it fire, so
    the decision is fully reconstructable by a human (auditability, NFR-3). Rule
    outputs are kept visibly distinct from model outputs (Layer Separation) and are
    labelled deterministic — never presented as a learned score.

    ``evidence`` mirrors the persisted ``rule_hits.evidence`` JSON (the assembler /
    audit writer map this domain type onto the ORM row, adding ids and timestamps).

    Spec: FR-6, FR-20, §6.5; Addendum §4.
    """

    model_config = ConfigDict(frozen=True)

    rule_id: str
    summary: str  # short human-readable statement for the evidence / explanation layers
    evidence: dict[str, float | int | bool | str | None]  # the fields + thresholds that fired
