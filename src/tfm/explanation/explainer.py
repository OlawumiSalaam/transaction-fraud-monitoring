"""Explainer interface + fallback orchestration (FR-10, FR-11, FR-12).

The Explainer turns the assembled ``EvidencePackage`` and the ``Recommendation``
into an ``Explanation`` — plain-language prose that *consumes* evidence and never
sources it (Addendum §4). Two implementations sit behind this interface:

- ``TemplatedExplainer`` (``templated.py``) — deterministic and **grounded by
  construction**: every sentence is generated from a named groundable element (or
  from the recommendation, which itself traces to elements), so every factual claim
  is reconstructable from the assembled evidence. Always available.
- ``LLMExplainer`` (``llm_explainer.py``) — a documented stub in V1; when enabled it
  is constrained to the groundable set and its output must pass the deterministic
  ``GroundingGate`` before any human sees it.

Fallback contract (NFR-2, FR-12): LLM disabled, unavailable, or grounding-failed →
the templated explanation is returned. There is no error path for LLM issues.

Spec references: FR-10, FR-11, FR-12, FR-13; §3, §5.5, §11.2; Addendum §4.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from tfm.recommendation.policy import Recommendation
from tfm.schema.evidence import EvidencePackage

Pathway = Literal["templated", "llm"]


class LLMUnavailable(RuntimeError):
    """Raised by the LLM explainer when it cannot produce output (triggers fallback)."""


class GroundingResult(BaseModel):
    """The grounding gate verdict (FR-11). ``verified`` gates the LLM path."""

    model_config = ConfigDict(frozen=True)

    verified: bool
    groundable_fields_used: tuple[str, ...]  # element ids that formed the reference set
    violations: tuple[str, ...] = ()  # ungrounded tokens (LLM-path failures)


class Explanation(BaseModel):
    """A grounded plain-language explanation (Addendum §4).

    ``ai_generated`` is always true: the prose is machine-generated (label shown by
    M7). ``pathway`` distinguishes the deterministic templated floor from the LLM.
    """

    model_config = ConfigDict(frozen=True)

    text: str
    pathway: Pathway
    ai_generated: bool = True
    grounding: GroundingResult


@runtime_checkable
class Explainer(Protocol):
    """The explanation interface consumed by the online path (Addendum §4)."""

    def explain(self, package: EvidencePackage, recommendation: Recommendation) -> Explanation: ...


def explain(
    package: EvidencePackage,
    recommendation: Recommendation,
    *,
    llm_enabled: bool = False,
) -> Explanation:
    """Produce the explanation, applying the graceful-degradation fallback.

    Order: LLM (if enabled) -> grounding gate -> pass ? LLM : templated. The
    templated explanation is always computed and is returned whenever the LLM is
    disabled, unavailable, or fails grounding. Never raises for LLM issues (NFR-2).
    """
    # Imported lazily to avoid an import cycle (templated/grounding import this module).
    from tfm.explanation.templated import TemplatedExplainer

    templated = TemplatedExplainer().explain(package, recommendation)
    if not llm_enabled:
        return templated

    from tfm.explanation.grounding import GroundingGate
    from tfm.explanation.llm_explainer import LLMExplainer

    try:
        candidate = LLMExplainer().explain(package, recommendation)
    except LLMUnavailable:
        return templated

    result = GroundingGate().verify(candidate.text, package, recommendation)
    if result.verified:
        return Explanation(text=candidate.text, pathway="llm", grounding=result)
    return templated
