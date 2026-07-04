"""Deterministic rule definitions for the documented fraud typology (FR-6).

Each definition is a pure function ``(FeatureVector, params) -> RuleHit | None`` over
the shared canonical feature substrate. Rules are auditable if-then only — no
probabilistic step and no dependence on the ML score (Addendum §4). Parameters come
from ``config/rules.yaml``; the logic contains no literals.

Balance/sequence features (``frac_bal_orig_moved``, ``orig_account_emptied``) are used
here legitimately: §6.5 names them as the balance/sequence family for the rule engine
and FR-6 names the account-draining pattern. The IMP-011 leakage quarantine applied
only to the ML scorer's *learned* dependence, not to transparent deterministic rules.

Real definitions (evaluate on a single-transaction FeatureVector):
- ``account_draining``      — a large fraction of the origin balance moved (§6.5).
- ``velocity``              — a transaction-count spike in the trailing 24 h window.
- ``new_beneficiary_large`` — a large amount to a first-seen counterparty.

Extension-point stub (documented no-op behind the interface — IC-M3-01):
- ``mule_passthrough``      — the inbound-then-outbound signature (§6.5) needs
  cross-transaction peer context (the M4 assembler's assembled evidence); it is not
  present on a single-transaction FeatureVector. Activated in M4.

Spec references: FR-6, FR-7, §6.5, §6.6; Addendum §4; Release Plan M3; IMP-011.
"""

from __future__ import annotations

from collections.abc import Callable

from tfm.schema.evidence import FeatureVector, RuleHit

RuleDefinition = Callable[[FeatureVector, dict[str, float]], "RuleHit | None"]


def account_draining(features: FeatureVector, params: dict[str, float]) -> RuleHit | None:
    """Fire when a large fraction of the origin balance moves in one transaction.

    PaySim's signature draining pattern (§6.6). Uses the canonical balance/sequence
    feature ``frac_bal_orig_moved`` (§6.5); None (undefined fraction, zero prior
    balance) never fires.
    """
    threshold = params["min_fraction_of_balance"]
    frac = features.frac_bal_orig_moved
    if frac is None or frac < threshold:
        return None
    return RuleHit(
        rule_id="account_draining",
        summary=f"{frac:.0%} of the origin balance moved in one transaction (>= {threshold:.0%})",
        evidence={
            "frac_bal_orig_moved": frac,
            "min_fraction_of_balance": threshold,
            "orig_account_emptied": features.orig_account_emptied,
            "amount": features.amount,
            "bal_orig_before": features.bal_orig_before,
        },
    )


def velocity(features: FeatureVector, params: dict[str, float]) -> RuleHit | None:
    """Fire on a transaction-count spike in the trailing window.

    Reads the canonical ``txn_count_24h`` (the M1 account-behavioural 24 h sliding
    window). The window is fixed by that feature at 24 h; ``window_hours`` in config
    is recorded as evidence and is expected to match.
    """
    max_transactions = params["max_transactions"]
    count = features.txn_count_24h
    if count < max_transactions:
        return None
    return RuleHit(
        rule_id="velocity",
        summary=f"{count} transactions in the trailing 24 h window (>= {int(max_transactions)})",
        evidence={
            "txn_count_24h": count,
            "max_transactions": max_transactions,
            "window_hours": params.get("window_hours", 24.0),
        },
    )


def new_beneficiary_large(features: FeatureVector, params: dict[str, float]) -> RuleHit | None:
    """Fire on a large amount to a first-seen counterparty (new-beneficiary + large).

    Uses the canonical ``is_new_counterparty`` and ``amount`` — a single-transaction
    signature of funds directed to a fresh mule/beneficiary (§6.5 counterparty family).
    """
    threshold = params["amount_threshold"]
    if not features.is_new_counterparty or features.amount < threshold:
        return None
    return RuleHit(
        rule_id="new_beneficiary_large",
        summary=f"{features.amount:,.0f} to a first-seen counterparty (>= {threshold:,.0f})",
        evidence={
            "amount": features.amount,
            "amount_threshold": threshold,
            "is_new_counterparty": True,
            "counterparty_id": features.counterparty_id,
        },
    )


def mule_passthrough(features: FeatureVector, params: dict[str, float]) -> RuleHit | None:
    """Documented no-op (IC-M3-01).

    The inbound-then-rapid-outbound mule signature (§6.5) is inherently
    cross-transaction: it requires knowing the account received funds and is
    forwarding ~that amount within a window. That linkage is the M4 assembler's
    assembled-evidence responsibility (Addendum §4 — the rule engine's input is
    "the assembled evidence for a transaction"); it is not present on a
    single-transaction ``FeatureVector``, and it must not be approximated with the
    remediation-specific ``hours_since_last_txn`` (which measures the gap to the
    prior *outbound* row, not an inbound-then-outbound passthrough). This definition
    is registered behind the interface and never fires until M4 supplies peer
    evidence. See IC-M3-01 in PROGRESS.md.
    """
    return None


# All four FR-6 rule ids resolve to a definition; the config validator
# (RulesConfig) guarantees only KNOWN_RULE_IDS can be enabled, and the coherence
# test asserts REGISTRY covers exactly KNOWN_RULE_IDS.
REGISTRY: dict[str, RuleDefinition] = {
    "account_draining": account_draining,
    "velocity": velocity,
    "new_beneficiary_large": new_beneficiary_large,
    "mule_passthrough": mule_passthrough,
}
