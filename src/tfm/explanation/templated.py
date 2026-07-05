"""Templated explanation: deterministic, grounded by construction (FR-12).

Every sentence is generated from a named groundable ``EvidenceElement`` (or from the
recommendation, which itself traces to elements). Numbers are rendered losslessly and
entities are copied verbatim from the elements, so every factual claim is
reconstructable from the assembled evidence — the explanation is grounded by
construction and provably passes the grounding gate (it therefore bypasses it).

The explainer *consumes* evidence; it never sources it (Addendum §4). It explains the
assembled evidence and the recommendation — not model internals (the scorer is
operationally excluded under FR-4).

Spec references: FR-10, FR-12, FR-13; §11.2; Addendum §4.
"""

from __future__ import annotations

from tfm.explanation.explainer import Explanation, GroundingResult
from tfm.recommendation.policy import Recommendation
from tfm.schema.evidence import EvidenceElement, EvidencePackage


def _text(element: EvidenceElement, key: str) -> str:
    return str(element.raw.get(key, ""))


def _amount(element: EvidenceElement, key: str) -> float:
    value = element.raw.get(key)
    return float(value) if isinstance(value, int | float) else 0.0


class TemplatedExplainer:
    """Deterministic, grounded-by-construction explainer (always available)."""

    def explain(self, package: EvidencePackage, recommendation: Recommendation) -> Explanation:
        by_id = {e.element_id: e for e in package.elements}
        statements: list[tuple[str, tuple[str, ...]]] = []

        # 1. What happened (requirement 1).
        if "txn_facts" in by_id:
            facts = by_id["txn_facts"]
            statements.append(
                (
                    f"A {_text(facts, 'type')} of {_amount(facts, 'amount'):,.2f} moved from "
                    f"account {_text(facts, 'account_id')} to {_text(facts, 'counterparty_id')} "
                    f"on {_text(facts, 'event_ts')}.",
                    ("txn_facts",),
                )
            )

        # 2. Why flagged: the fired deterministic rules, read as investigation findings.
        rule_elements = [e for e in package.elements if e.source == "rule"]
        if rule_elements:
            for element in rule_elements:
                statements.append((f"{_text(element, 'summary')}.", (element.element_id,)))
        else:
            statements.append(
                ("No deterministic rule matched this transaction.", ("interpretable_features",))
            )

        # 3. Abnormal for this account, or the explicit no-baseline state (requirement 3).
        if "account_baseline" in by_id:
            baseline = by_id["account_baseline"]
            if "reason" in baseline.raw:
                statements.append(
                    (
                        "This is the account's first observed transaction, so there is no "
                        "behavioural baseline to compare against.",
                        ("account_baseline",),
                    )
                )
            else:
                prior = int(_amount(baseline, "prior_transaction_count"))
                recent = int(_amount(baseline, "txn_count_24h"))
                statements.append(
                    (
                        f"The account has {prior} prior transactions, "
                        f"{recent} in the last 24 hours.",
                        ("account_baseline",),
                    ),
                )

        # 6. The score, or its honest FR-4 exclusion (requirement 6).
        if "score_signal" in by_id:
            score = by_id["score_signal"]
            if str(score.raw.get("status")) == "excluded":
                statements.append(
                    (
                        "No model score is available — model scoring is excluded by the "
                        "leakage gate — so this assessment rests on the deterministic "
                        "findings above.",
                        ("score_signal",),
                    )
                )
            else:
                statements.append(
                    (f"Model risk score: {_amount(score, 'probability'):.4f}.", ("score_signal",))
                )

        # Recommendation (advisory; traces to the rule and score elements).
        rec_sources = tuple(f"rule:{rid}" for rid in recommendation.basis.rule_ids) or (
            "score_signal",
        )
        uncertain = (
            " This assessment carries some uncertainty." if recommendation.uncertainty_flag else ""
        )
        statements.append(
            (
                f"Recommended action: {recommendation.action} "
                f"({recommendation.confidence} confidence).{uncertain}",
                rec_sources,
            )
        )

        text = " ".join(sentence for sentence, _ in statements)
        fields_used: list[str] = []
        for _, sources in statements:
            for source in sources:
                if source not in fields_used:
                    fields_used.append(source)

        return Explanation(
            text=text,
            pathway="templated",
            grounding=GroundingResult(verified=True, groundable_fields_used=tuple(fields_used)),
        )
