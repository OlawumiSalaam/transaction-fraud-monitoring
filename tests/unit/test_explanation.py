"""Unit tests for M6 — templated explainer, grounding gate, graceful fallback.

Verifies: the templated explanation is grounded by construction (its own output
passes the deterministic gate); the gate catches planted ungrounded numbers/entities
with canonical normalization (R4); the fallback returns templated on LLM
unavailability (NFR-2); and the five graceful-degradation states produce honest text.

Spec: FR-10, FR-11, FR-12, FR-13, FR-24; Addendum §4.
"""

from __future__ import annotations

from datetime import UTC, datetime

from tfm.assembly.assembler import assemble_evidence
from tfm.config.settings import RecommendationConfig, ScoreBandsConfig, ThresholdsConfig
from tfm.explanation.explainer import Explanation, explain
from tfm.explanation.grounding import GroundingGate
from tfm.explanation.templated import TemplatedExplainer
from tfm.recommendation.policy import recommend
from tfm.schema.entities import Counterparty, Transaction, TransactionType
from tfm.schema.evidence import EvidencePackage, FeatureVector, RuleHit, ScoreStatus

_TXN = Transaction(
    txn_id="paysim-0004116",
    step=212,
    event_ts=datetime(2024, 1, 9, 20, 0, 0, tzinfo=UTC),
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
_CONFIG = ThresholdsConfig(
    score_bands=ScoreBandsConfig(low_max=0.30, high_min=0.80),
    recommendation=RecommendationConfig(escalating_rules=["account_draining"]),
)


def _features(**overrides: object) -> FeatureVector:
    base: dict[str, object] = {
        "txn_id": _TXN.txn_id,
        "account_id": _TXN.account_id,
        "counterparty_id": _TXN.counterparty_id,
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


def _excluded() -> ScoreStatus:
    return ScoreStatus(
        available=False,
        model_version_id="tfm-scorer-20260704053632",
        leakage_verdict="fail",
        exclusion_reason="failed the simulator-leakage gate; excluded from operational scoring",
    )


def _pipeline(
    *, prior_transaction_count: int = 0, rule_hits: list[RuleHit] | None = None
) -> tuple[EvidencePackage, Explanation]:
    features = _features()
    hits = rule_hits or []
    package = assemble_evidence(
        transaction=_TXN,
        features=features,
        prior_transaction_count=prior_transaction_count,
        counterparty=Counterparty(counterparty_id=_TXN.counterparty_id, is_merchant=False),
        score=_excluded(),
        rule_hits=hits,
    )
    recommendation = recommend(score=_excluded(), rule_hits=hits, config=_CONFIG)
    explanation = explain(package, recommendation)
    return package, explanation


def _drain_hit() -> RuleHit:
    return RuleHit(
        rule_id="account_draining",
        summary="100% of the origin balance moved in one transaction (>= 90%)",
        evidence={"frac_bal_orig_moved": 1.0, "min_fraction_of_balance": 0.9, "amount": 441423.0},
    )


def _nbl_hit() -> RuleHit:
    return RuleHit(
        rule_id="new_beneficiary_large",
        summary="441,423 to a first-seen counterparty (>= 200,000)",
        evidence={"amount": 441423.0, "amount_threshold": 200000.0, "is_new_counterparty": True},
    )


# ── Templated explanation is grounded by construction ─────────────────────────


def test_templated_output_passes_the_gate() -> None:
    hits = [_drain_hit(), _nbl_hit()]
    package, explanation = _pipeline(rule_hits=hits)
    assert explanation.pathway == "templated"
    recommendation = recommend(score=_excluded(), rule_hits=hits, config=_CONFIG)
    result = GroundingGate().verify(explanation.text, package, recommendation)
    assert result.verified is True, f"ungrounded tokens: {result.violations}"


def test_templated_is_deterministic_and_labelled() -> None:
    _, first = _pipeline(rule_hits=[_drain_hit()])
    _, second = _pipeline(rule_hits=[_drain_hit()])
    assert first == second
    assert first.ai_generated is True
    assert first.grounding.groundable_fields_used  # provenance recorded


# ── Grounding gate catches hallucinations (R4/R5) ─────────────────────────────


def test_gate_rejects_ungrounded_number() -> None:
    package, _ = _pipeline(rule_hits=[_drain_hit()])
    recommendation = recommend(score=_excluded(), rule_hits=[_drain_hit()], config=_CONFIG)
    bad = "The amount was 999,999.00 which is suspicious."
    result = GroundingGate().verify(bad, package, recommendation)
    assert result.verified is False
    assert "999,999.00" in result.violations


def test_gate_rejects_ungrounded_entity() -> None:
    package, _ = _pipeline(rule_hits=[_drain_hit()])
    recommendation = recommend(score=_excluded(), rule_hits=[_drain_hit()], config=_CONFIG)
    result = GroundingGate().verify("Funds went to account C9999999999.", package, recommendation)
    assert result.verified is False


def test_gate_normalizes_currency_and_percent() -> None:
    # Grounded values expressed with $, commas, and % must pass (R4 normalization).
    package, _ = _pipeline(rule_hits=[_drain_hit()])
    recommendation = recommend(score=_excluded(), rule_hits=[_drain_hit()], config=_CONFIG)
    text = "Moved $441,423.00 which is 100% of the balance (threshold 90%)."
    assert GroundingGate().verify(text, package, recommendation).verified is True


# ── Graceful fallback (NFR-2) ─────────────────────────────────────────────────


def test_llm_disabled_returns_templated() -> None:
    _, explanation = _pipeline(rule_hits=[_drain_hit()])
    assert explanation.pathway == "templated"


def test_llm_enabled_stub_falls_back_to_templated() -> None:
    package, _ = _pipeline(rule_hits=[_drain_hit()])
    recommendation = recommend(score=_excluded(), rule_hits=[_drain_hit()], config=_CONFIG)
    explanation = explain(package, recommendation, llm_enabled=True)  # stub raises -> fallback
    assert explanation.pathway == "templated"


# ── Five graceful-degradation states (honest, no invented info) ───────────────


def test_state_scorer_excluded() -> None:
    _, explanation = _pipeline(rule_hits=[_drain_hit()])
    assert "excluded by the leakage gate" in explanation.text  # governance mode, no invented score


def test_state_no_baseline() -> None:
    _, explanation = _pipeline(prior_transaction_count=0, rule_hits=[_drain_hit()])
    assert "behavioural baseline" in explanation.text
    assert "first observed transaction" in explanation.text


def test_state_no_rules_fire() -> None:
    _, explanation = _pipeline(rule_hits=[])
    assert "No deterministic rule matched" in explanation.text
    assert "escalate" not in explanation.text  # honest: no rule -> hold, not escalate


def test_state_one_rule_fires() -> None:
    _, explanation = _pipeline(rule_hits=[_drain_hit()])
    assert "origin balance moved" in explanation.text  # the draining finding
    assert "escalate" in explanation.text


def test_state_multiple_rules_fire() -> None:
    _, explanation = _pipeline(rule_hits=[_drain_hit(), _nbl_hit()])
    assert "origin balance moved" in explanation.text
    assert "first-seen counterparty" in explanation.text


def test_explainer_protocol_is_satisfied() -> None:
    from tfm.explanation.explainer import Explainer

    assert isinstance(TemplatedExplainer(), Explainer)
