"""Unit tests for the Evidence Assembler (FR-2, M4).

Covers the seven evidence requirements, the total traceability invariant, the
element-centric groundable contract (Q2), and the two honest-degradation states:
the FR-4 score exclusion and the first-observed no-baseline element.

Spec: FR-2, FR-13; §265; Addendum §4.
"""

from __future__ import annotations

from datetime import UTC, datetime

from tfm.assembly.assembler import NO_BASELINE_REASON, assemble_evidence
from tfm.schema.entities import Counterparty, Transaction, TransactionType
from tfm.schema.evidence import EvidenceElement, FeatureVector, RuleHit, ScoreStatus

_ALLOWED_SOURCES = {
    "transaction",
    "account_history",
    "counterparty",
    "rule",
    "score_signal",
    "disclosure",
}
_EVENT_TS = datetime(2024, 1, 2, 3, 0, 0, tzinfo=UTC)


def _txn(**overrides: object) -> Transaction:
    base: dict[str, object] = {
        "txn_id": "paysim-0000001",
        "step": 3,
        "event_ts": _EVENT_TS,
        "type": TransactionType.TRANSFER,
        "amount": 441423.0,
        "account_id": "C1",
        "counterparty_id": "C900",
        "direction": "outbound",
        "bal_orig_before": 441423.0,
        "bal_orig_after": 0.0,
        "bal_dest_before": 0.0,
        "bal_dest_after": 441423.0,
        "sim_flagged": False,
        "label": True,
    }
    base.update(overrides)
    return Transaction(**base)  # type: ignore[arg-type]


def _features(**overrides: object) -> FeatureVector:
    base: dict[str, object] = {
        "txn_id": "paysim-0000001",
        "account_id": "C1",
        "counterparty_id": "C900",
        "amount": 441423.0,
        "type_payment": False,
        "type_transfer": True,
        "type_cash_out": False,
        "type_cash_in": False,
        "type_debit": False,
        "bal_orig_before": 441423.0,
        "bal_orig_after": 0.0,
        "bal_dest_before": 0.0,
        "bal_dest_after": 441423.0,
        "frac_bal_orig_moved": 1.0,
        "orig_account_emptied": True,
        "txn_count_24h": 0,
        "amount_sum_24h": 0.0,
        "is_new_counterparty": True,
        "distinct_counterparties_seen": 0,
    }
    base.update(overrides)
    return FeatureVector(**base)  # type: ignore[arg-type]


def _counterparty() -> Counterparty:
    return Counterparty(counterparty_id="C900", is_merchant=False)


def _excluded_score() -> ScoreStatus:
    return ScoreStatus(
        available=False,
        model_version_id="tfm-scorer-20260704053632",
        leakage_verdict="fail",
        exclusion_reason="failed the simulator-leakage gate; excluded from operational scoring",
    )


def _assemble(*, prior_transaction_count: int = 0, rule_hits: list[RuleHit] | None = None):
    return assemble_evidence(
        transaction=_txn(),
        features=_features(),
        prior_transaction_count=prior_transaction_count,
        counterparty=_counterparty(),
        score=_excluded_score(),
        rule_hits=rule_hits or [],
    )


def _by_id(pkg: object) -> dict[str, EvidenceElement]:
    return {e.element_id: e for e in pkg.elements}  # type: ignore[attr-defined]


# ── Seven evidence requirements ───────────────────────────────────────────────


def test_all_seven_requirements_are_covered() -> None:
    coverage = _assemble().requirement_coverage()
    assert set(coverage) == set(range(1, 8))
    for requirement, element_ids in coverage.items():
        assert element_ids, f"requirement {requirement} has no evidence element"


def test_rule_hits_answer_requirement_2() -> None:
    hit = RuleHit(rule_id="account_draining", summary="100% of balance moved", evidence={"x": 1.0})
    coverage = _assemble(rule_hits=[hit]).requirement_coverage()
    assert "rule:account_draining" in coverage[2]
    assert "interpretable_features" in coverage[2]


# ── Total traceability invariant (over every element) ─────────────────────────


def test_traceability_invariant_holds_for_every_element() -> None:
    pkg = _assemble(rule_hits=[RuleHit(rule_id="account_draining", summary="s", evidence={"a": 1})])
    assert pkg.elements  # non-empty
    for element in pkg.elements:  # TOTAL assertion, not a spot check
        assert element.source in _ALLOWED_SOURCES
        assert element.raw, f"{element.element_id} has empty raw"
        assert isinstance(element.groundable, bool)
        assert element.requirements
        assert all(1 <= r <= 7 for r in element.requirements)


def test_transaction_element_values_trace_to_the_transaction() -> None:
    pkg = _assemble()
    facts = _by_id(pkg)["txn_facts"]
    assert facts.raw["amount"] == 441423.0
    assert facts.raw["type"] == "TRANSFER"
    assert facts.raw["account_id"] == "C1"


# ── Element-centric groundable contract (Q2) ──────────────────────────────────


def test_expected_elements_are_groundable() -> None:
    hit = RuleHit(rule_id="account_draining", summary="s", evidence={})
    by_id = _by_id(_assemble(rule_hits=[hit]))
    for element_id in (
        "txn_facts",
        "interpretable_features",
        "account_baseline",
        "counterparty",
        "direction_balances",
        "score_signal",
        "rule:account_draining",
    ):
        assert by_id[element_id].groundable is True, f"{element_id} should be groundable"


def test_disclosure_is_display_only_not_groundable() -> None:
    disclosure = _by_id(_assemble())["disclosure:synthetic_data"]
    assert disclosure.source == "disclosure"
    assert disclosure.groundable is False


def test_groundable_set_is_the_groundable_subset() -> None:
    pkg = _assemble()
    groundable_ids = {e.element_id for e in pkg.groundable_elements}
    display_only_ids = {e.element_id for e in pkg.elements if not e.groundable}
    assert "disclosure:synthetic_data" in display_only_ids
    assert "disclosure:synthetic_data" not in groundable_ids
    # Completeness: every groundable element is present in the package's element list.
    assert groundable_ids <= {e.element_id for e in pkg.elements}


# ── Honest degradation: FR-4 score exclusion ──────────────────────────────────


def test_excluded_score_is_explicit_structured_element() -> None:
    score = _by_id(_assemble())["score_signal"]
    assert score.groundable is True
    assert score.raw["status"] == "excluded"
    assert score.raw["excluded_under"] == "FR-4"
    assert score.raw["leakage_verdict"] == "fail"
    assert score.raw["reason"]


def test_no_score_value_traces_to_any_groundable_element() -> None:
    # A score claim is structurally ungroundable: no probability anywhere.
    pkg = _assemble()
    for element in pkg.groundable_elements:
        assert "probability" not in element.raw


# ── Honest degradation: first-observed no-baseline ────────────────────────────


def test_first_observed_account_emits_groundable_no_baseline_element() -> None:
    baseline = _by_id(_assemble(prior_transaction_count=0))["account_baseline"]
    assert baseline.source == "account_history"
    assert baseline.groundable is True
    assert baseline.raw["reason"] == NO_BASELINE_REASON
    assert baseline.raw["prior_transaction_count"] == 0


def test_account_with_history_emits_behavioural_summary_not_no_baseline() -> None:
    baseline = _by_id(_assemble(prior_transaction_count=5))["account_baseline"]
    assert "reason" not in baseline.raw
    assert baseline.raw["prior_transaction_count"] == 5
    assert "txn_count_24h" in baseline.raw


# ── Determinism / purity ──────────────────────────────────────────────────────


def test_assembly_is_deterministic() -> None:
    assert _assemble().elements == _assemble().elements
