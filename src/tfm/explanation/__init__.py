"""LLM explainer, grounding gate, templated fallback (FR-10, FR-11, FR-12). Implemented in M6."""

from tfm.explanation.explainer import (
    Explainer,
    Explanation,
    GroundingResult,
    LLMUnavailable,
    explain,
)
from tfm.explanation.grounding import GroundingGate
from tfm.explanation.llm_explainer import LLMExplainer
from tfm.explanation.templated import TemplatedExplainer

__all__ = [
    "Explainer",
    "Explanation",
    "GroundingGate",
    "GroundingResult",
    "LLMExplainer",
    "LLMUnavailable",
    "TemplatedExplainer",
    "explain",
]
