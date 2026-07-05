"""Grounding Gate: deterministic post-check, ungrounded rate approx 0 (FR-11).

Deterministic code — **never a model** (Addendum §4). The gate builds a reference
set from the case's groundable ``EvidenceElement``s (the M4 contract) plus the
recommendation's controlled vocabulary, then verifies that every factual token in a
generated narrative traces to that set:

- **numbers** (amounts, percentages, counts, thresholds) — after canonical
  normalization (strip ``$`` and thousands separators; map ``%`` to a fraction), so
  ``"$441,423.00"`` == ``441423.0`` and ``"90%"`` == ``0.9`` (R4);
- **entities and controlled terms** (account/counterparty/txn ids, transaction
  types, rule identifiers, model version ids, ``FR-4``, the recommendation action /
  confidence / score band) — grounded strings are masked out first, then any
  residual id-/type-/rule-shaped token is an ungrounded violation.

``pass`` implies every numeric and entity token in the narrative is present in the
reference set. On failure the orchestrator falls back to the templated explanation.
The templated path is grounded by construction and bypasses the gate.

Spec references: FR-11, FR-24, §8, §357; Addendum §4; Risk R4/R5.
"""

from __future__ import annotations

import re

from tfm.explanation.explainer import GroundingResult
from tfm.recommendation.policy import Recommendation
from tfm.schema.evidence import EvidencePackage

# A numeric literal: optional $, digits with optional thousands separators, optional
# decimals, optional trailing percent.
_NUMBER_RE = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")

# Tokens that look like grounded entities; any left unmasked is an ungrounded claim.
_ENTITY_SHAPE_RE = re.compile(
    r"\bC\d{3,}\b"
    r"|\bM\d+\b"
    r"|\bpaysim-\d+\b"
    r"|\btfm-scorer-\w+\b"
    r"|\b(?:PAYMENT|TRANSFER|CASH_OUT|CASH_IN|DEBIT)\b"
    r"|\b(?:account_draining|velocity|new_beneficiary_large|mule_passthrough)\b"
    r"|\bFR-\d+\b"
)


def _normalize_number(token: str) -> float | None:
    body = token.replace("$", "").replace(",", "")
    is_percent = body.endswith("%")
    if is_percent:
        body = body[:-1]
    try:
        value = float(body)
    except ValueError:
        return None
    if is_percent:
        value /= 100.0
    return round(value, 6)


def _reference(
    package: EvidencePackage, recommendation: Recommendation
) -> tuple[set[float], list[str]]:
    """Build the (numbers, grounded-strings) reference from groundable elements."""
    numbers: set[float] = set()
    strings: set[str] = set()
    for element in package.groundable_elements:
        for value in element.raw.values():
            if isinstance(value, bool):
                continue  # bool is an int subclass; not a groundable number
            if isinstance(value, int | float):
                numbers.add(round(float(value), 6))
            elif isinstance(value, str) and value:
                strings.add(value)
    # The recommendation's controlled vocabulary also traces to elements.
    strings.update(
        {recommendation.action, recommendation.confidence, recommendation.basis.score_band}
    )
    strings.update(recommendation.basis.rule_ids)
    # Mask longest strings first so shorter substrings inside them are already gone.
    ordered_strings = sorted(strings, key=len, reverse=True)
    return numbers, ordered_strings


class GroundingGate:
    """Deterministic verification that every claim traces to a groundable element."""

    def verify(
        self, text: str, package: EvidencePackage, recommendation: Recommendation
    ) -> GroundingResult:
        numbers, grounded_strings = _reference(package, recommendation)

        masked = text
        for grounded in grounded_strings:
            # Longest-first substring replacement: robust for grounded strings that
            # end in punctuation (e.g. rule summaries) where a word boundary fails.
            masked = masked.replace(grounded, " ")

        violations: list[str] = []
        for token in _NUMBER_RE.findall(masked):
            value = _normalize_number(token)
            if value is not None and value not in numbers:
                violations.append(token)
        violations.extend(_ENTITY_SHAPE_RE.findall(masked))

        used = tuple(e.element_id for e in package.groundable_elements)
        return GroundingResult(
            verified=not violations,
            groundable_fields_used=used,
            violations=tuple(violations),
        )
