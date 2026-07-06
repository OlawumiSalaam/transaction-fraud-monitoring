"""Presentation helpers for the analyst workspace.

Pure functions — no Streamlit imports — so the analyst-facing mapping (product
language) and the no-default disposition control are unit-testable. These map the
API's composed objects into analyst language; they contain no fraud, model, or
explanation logic.
"""

from __future__ import annotations

from typing import Any

# Internal rule ids / elements → analyst-facing risk-indicator labels (the brief's
# "fraud-risk indicators"). The analyst never sees the internal ids.
_RULE_LABELS: dict[str, str] = {
    "account_draining": "Account draining detected",
    "new_beneficiary_large": "Large transfer to a new beneficiary",
    "velocity": "Rapid transaction activity",
    "mule_passthrough": "Pass-through / mule pattern",
}
_ACTION_BADGES: dict[str, str] = {"escalate": "ESCALATE", "hold": "HOLD", "clear": "CLEAR"}


def risk_indicators(case_view: dict[str, Any]) -> list[dict[str, str]]:
    """The 'Risk Indicators Detected' rows — each drillable to its raw signal."""
    indicators: list[dict[str, str]] = []
    for element in case_view["evidence"]["elements"]:
        if element["source"] == "rule":
            rule_id = str(element["raw"].get("rule_id", ""))
            indicators.append(
                {"label": _RULE_LABELS.get(rule_id, rule_id), "element_id": element["element_id"]}
            )
        elif element["element_id"] == "account_baseline" and "reason" in element["raw"]:
            indicators.append({"label": "First observed account", "element_id": "account_baseline"})
    return indicators


def decision_basis_note(case_view: dict[str, Any]) -> str:
    """Graceful-degradation copy shown within the Recommended Action area.

    Legible and understated but unmissable: the analyst leaves knowing the model
    number is intentionally withheld (a governance control), not missing.
    """
    if case_view["recommendation"]["basis"]["score_band"] == "none":
        return (
            "Model scoring is excluded by the leakage gate — "
            "this case is assessed on verified rule evidence."
        )
    return "Assessed on the model score and deterministic rules."


def action_badge(action: str) -> str:
    return _ACTION_BADGES.get(action, action.upper())


def disposition_control(options: list[str] | tuple[str, ...]) -> dict[str, Any]:
    """The disposition control spec: options with NO default selection.

    ``index=None`` renders unselected on Streamlit 1.58; the sentinel + a disabled
    submit-until-chosen enforce the boundary even on an older build.
    """
    return {"options": list(options), "index": None, "placeholder": "— select a disposition —"}


def rationale_required(action: str, recommended_action: str) -> bool:
    """Client-side hint (server-enforced): escalate or a deviation needs a rationale."""
    return action == "escalate" or action != recommended_action
