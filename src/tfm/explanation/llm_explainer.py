"""LLM explainer: constrained to the groundable set.

Version 1 ships on the templated floor: the LLM is a **documented stub behind the
real Explainer interface**. When enabled in
a future version it would render the groundable evidence into prose under a
constrained, evidence-scoped prompt, and its output would be verified by the
deterministic ``GroundingGate`` before any human sees it.

As a stub it raises ``LLMUnavailable`` so the orchestrator falls back to the templated
explanation — exercising and proving the graceful-degradation path. It
never fabricates output. Upgrading to a minimal single provider is a
configuration/implementation change behind this interface, not an architecture change.
"""

from __future__ import annotations

from tfm.explanation.explainer import Explanation, LLMUnavailable
from tfm.recommendation.policy import Recommendation
from tfm.schema.evidence import EvidencePackage


class LLMExplainer:
    """Documented V1 stub: not enabled; always defers to the templated fallback."""

    def explain(self, package: EvidencePackage, recommendation: Recommendation) -> Explanation:
        raise LLMUnavailable(
            "LLM explainer is a documented V1 stub (templated floor ships); "
            "no provider is configured (backlog B8)."
        )
