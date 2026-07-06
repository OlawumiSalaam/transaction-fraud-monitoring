"""Shared evidence schema: FeatureVector and RuleHit.

The assembled Case evidence record and groundable evidence set are completed.
This module provides the shared spine those layers import:

- ``FeatureVector`` — the output of the Feature Builder (data/features.py),
  shared by the rule engine and the evidence assembler. The ML scorer
  trains on the ``PRIMARY_FEATURE_COLUMNS`` subset (balance artifacts
  quarantined), not on the full vector verbatim.
- ``RuleHit`` — a deterministic rule firing, produced by the rule engine
  and consumed by the assembler, recommendation policy, and audit.

A feature that is predictive but not interpretable is disqualified: the rule
engine and the LLM grounding layer require every field to be human-readable.
sim_flagged is never present: it is ingested for provenance but
excluded from all features to prevent trivial simulator leakage.
Architectural responsibility: shared spine — scorer, rules, and assembler all
import these types, never a private feature or hit shape.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class FeatureVector(BaseModel):
    """Point-in-time feature vector produced by the Feature Builder.

    The three consumers share this exact type:
    - Scorer (ML layer): uses numeric columns as input to the calibrated model.
    - Rule Engine (deterministic logic): reads named fields in auditable if-then
      rules (e.g., ``frac_bal_orig_moved`` for account-draining, ``is_new_counterparty``
      for new-beneficiary detection).
    - Evidence Assembler: selects fields for the groundable evidence set
      so the LLM can reference only known, human-readable values.

    None values encode «not applicable» (e.g., ``bal_dest_before`` is None for
    merchant counterparties that carry no balance signal). The ML scorer
    must impute or drop None/NaN fields before passing the matrix to sklearn.

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

    # ── Balance / sequence — both sides preserved (C4) ─────────────────
    bal_orig_before: float
    bal_orig_after: float
    bal_dest_before: float | None  # None for merchant counterparties
    bal_dest_after: float | None  # None for merchant counterparties

    # Derived balance signals: load-bearing for account-draining
    frac_bal_orig_moved: float | None  # amount / bal_orig_before; None if balance == 0
    orig_account_emptied: bool  # bal_orig_before > 0 and bal_orig_after == 0

    # ── Account-behavioural (24 h trailing window, point-in-time) ────────────
    txn_count_24h: int
    amount_sum_24h: float

    # ── Counterparty ─────────────────────────────────────────────────────────
    is_new_counterparty: bool
    distinct_counterparties_seen: int

    # ── Account-baseline deviation & sequence (point-in-time) ────
    # None on an account's first transaction (no prior baseline). Defaulted to
    # None so the (always-None-on-first-txn) signals need not be restated at
    # every construction site; build_features' to_feature_vector always populates
    # them. amount_to_prior_max_ratio is a bounded engineering extension; the
    # other two directly implement (deviation-from-baseline; sequence signal).
    amount_to_prior_mean_ratio: float | None = None  # amount / mean(prior amounts)
    amount_to_prior_max_ratio: float | None = None  # amount / max(prior amounts)
    hours_since_last_txn: float | None = None  # hours since the account's prior txn


class RuleHit(BaseModel):
    """A deterministic rule firing, preserved as auditable evidence.

    The rule engine produces these from the shared ``FeatureVector``. Each hit
    names the rule and carries the exact fields and thresholds that made it fire, so
    the decision is fully reconstructable by a human (auditability). Rule
    outputs are kept visibly distinct from model outputs (Layer Separation) and are
    labelled deterministic — never presented as a learned score.

    ``evidence`` mirrors the persisted ``rule_hits.evidence`` JSON (the assembler /
    audit writer map this domain type onto the ORM row, adding ids and timestamps).
    """

    model_config = ConfigDict(frozen=True)

    rule_id: str
    summary: str  # short human-readable statement for the evidence / explanation layers
    evidence: dict[str, float | int | bool | str | None]  # the fields + thresholds that fired


# ── Assembled evidence ───────────────────────────────────────────────────
#
# The Evidence Assembler (assembly/assembler.py) produces an EvidencePackage per
# flagged transaction, answering the seven evidence requirements and
# defining the groundable evidence set — the formal contract with the grounding
# gate. The contract is element-centric: the groundable set is the subset of
# EvidenceElements marked groundable, with a single completeness invariant —
# *every value or entity may reference must trace to a groundable
# EvidenceElement* — so there are no parallel numeric/entity collections to keep
# synchronised.

# The evidence sources an element may derive from. "disclosure" is a
# display-only source (never grounded) added for the synthetic-data disclosure
# (requirement 7).
EvidenceSource = Literal[
    "transaction",
    "account_history",
    "counterparty",
    "rule",
    "score_signal",
    "disclosure",
]

# Scalar value types permitted inside an element's raw payload / a rule hit.
EvidenceScalar = float | int | bool | str | None


class EvidenceElement(BaseModel):
    """One atomic, traceable unit of case evidence.

    Every element traces to a canonical field, a rule hit, or a score signal (the
    assembler's total traceability invariant). ``groundable`` marks whether may
    cite this element's values/entities: evidentiary elements are groundable;
    display-only elements (disclosures, contextual markers) are not — they are
    shown to the analyst but are not evidentiary claims about the risk, so
    the grounded narrative must not draw on them.

    ``requirements`` records which of the seven evidence requirements (1..7)
    this element helps answer; the package derives its coverage map from these, so
    there is no separately-maintained requirement index.
    """

    model_config = ConfigDict(frozen=True)

    element_id: str
    label: str
    source: EvidenceSource
    raw: dict[str, EvidenceScalar]
    groundable: bool
    requirements: tuple[int, ...] = ()


class ScoreStatus(BaseModel):
    """Input to the assembler describing the operational score's availability.

    In Version 1 the scorer is gate-ineligible, so ``available`` is False and
    the assembler emits an honest exclusion ``score_signal`` element carrying the
    reason but **no probability** — so no score value traces to any element and a
    score claim is structurally ungroundable (Q1). The ``available`` branch is
    defined for when an eligible model version exists; does not reintroduce the
    scorer into operational decisions.
    """

    model_config = ConfigDict(frozen=True)

    available: bool
    model_version_id: str
    probability: float | None = None  # present iff available
    calibrated: bool | None = None  # present iff available
    leakage_verdict: str | None = None  # present iff excluded (e.g. "fail")
    exclusion_reason: str | None = None  # present iff excluded


class EvidencePackage(BaseModel):
    """The assembled evidence for one flagged transaction(push output).

    Element-centric: ``elements`` is the single source of truth. The groundable set
    and the seven-requirements coverage map are both derived from the elements, so
    nothing parallel must be kept in sync. The recommendation and explanation
    are populated downstream — they are not part of this output.
    """

    model_config = ConfigDict(frozen=True)

    txn_id: str
    elements: tuple[EvidenceElement, ...]

    @property
    def groundable_elements(self) -> tuple[EvidenceElement, ...]:
        """The explicit groundable set: the subset may reference (Q2 contract)."""
        return tuple(e for e in self.elements if e.groundable)

    def requirement_coverage(self) -> dict[int, tuple[str, ...]]:
        """Map each of the seven evidence requirements to the element_ids answering it."""
        coverage: dict[int, list[str]] = {r: [] for r in range(1, 8)}
        for element in self.elements:
            for requirement in element.requirements:
                coverage[requirement].append(element.element_id)
        return {r: tuple(ids) for r, ids in coverage.items()}
