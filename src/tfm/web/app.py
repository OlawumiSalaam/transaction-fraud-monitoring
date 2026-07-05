"""Streamlit analyst workspace (M7).

Two screens over the FastAPI online path: the triage queue and the case view.
Business logic stays behind the API; this module only renders and orchestrates
HTTP calls. Analyst-facing language and the no-default disposition control come
from ``render.py`` (pure, tested). No fraud/model/explanation logic lives here.

Would a fraud analyst understand what to do within 30 seconds? That is the bar.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import streamlit as st

from tfm.web import render

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
_REASON_CODES = [
    "confirmed_fraud",
    "likely_fraud",
    "needs_review",
    "legitimate",
    "insufficient_info",
]

st.set_page_config(page_title="Fraud Case Workspace", layout="wide")


def _get(path: str, **params: Any) -> Any:
    query = {k: v for k, v in params.items() if v}
    resp = httpx.get(f"{API_BASE_URL}{path}", params=query, timeout=10.0)
    resp.raise_for_status()
    return resp.json()


def _open(case_id: str) -> None:
    st.session_state["case_id"] = case_id


def _close() -> None:
    st.session_state.pop("case_id", None)


def _queue_screen() -> None:
    st.title("Triage queue")
    cols = st.columns(4)
    level = cols[0].selectbox("Recommended level", ["all", "escalate", "hold"], index=0)
    rule = cols[1].selectbox(
        "Fired rule", ["any", "account_draining", "new_beneficiary_large", "velocity"], index=0
    )
    min_amount = cols[2].number_input("Min amount", min_value=0.0, value=0.0, step=1000.0)
    sort = cols[3].selectbox("Sort by", ["risk", "case_age"], index=0)

    data = _get(
        "/api/queue",
        sort=sort,
        level=None if level == "all" else level,
        rule=None if rule == "any" else rule,
        min_amount=min_amount or None,
    )
    st.caption(
        f"Sorted by: {data['ordering_basis']} ({data['order']}) · {len(data['items'])} open cases"
    )

    for item in data["items"]:
        row = st.columns([1, 2, 2, 3, 1])
        row[0].markdown(f"**{render.action_badge(item['action'])}**")
        row[1].write(f"{item['amount']:,.2f}")
        row[2].write(item["type"])
        row[3].write(", ".join(item["rule_ids"]) or "—")
        row[4].button(
            "Open", key=f"open-{item['case_id']}", on_click=_open, args=(item["case_id"],)
        )


def _case_screen(case_id: str) -> None:
    case = _get(f"/api/cases/{case_id}")
    st.button("← Back to queue", on_click=_close)

    txn = case["transaction"]
    rec = case["recommendation"]

    # WHAT HAPPENED
    st.subheader("What happened")
    st.write(
        f"**{txn['type']}** · {txn['amount']:,.2f} · {txn['account_id']} → "
        f"{txn['counterparty_id']} · {txn['event_ts']}"
    )

    # RECOMMENDED ACTION (dominant) — Decision Basis as supporting context.
    st.markdown(f"### ⯈ Recommended action: {render.action_badge(rec['action'])}")
    st.caption(
        f"Advisory — you decide · confidence: {rec['confidence']}"
        + (" · flagged uncertain" if rec["uncertainty_flag"] else "")
    )
    st.info(render.decision_basis_note(case))

    # WHY THIS CASE? (explanation)
    st.subheader("Why this case?")
    st.write(case["explanation"]["text"])
    st.caption(f"AI-generated · {case['explanation']['pathway']} · every claim traced to evidence")

    # RISK INDICATORS DETECTED (drill-down)
    st.subheader("Risk Indicators Detected")
    for indicator in render.risk_indicators(case):
        with st.expander(indicator["label"]):
            raw = _get(f"/api/cases/{case_id}/evidence/{indicator['element_id']}")["raw"]
            st.json(raw)
    disclosure = next(
        (e for e in case["evidence"]["elements"] if e["source"] == "disclosure"), None
    )
    if disclosure:
        st.caption(disclosure["raw"].get("synthetic_data", ""))

    # YOUR DECISION (nothing pre-selected)
    st.subheader("Your decision")
    control = render.disposition_control(case["disposition_options"])
    action = st.radio(
        "Disposition", control["options"], index=control["index"], key=f"disp-{case_id}"
    )
    reason_code = st.selectbox("Reason code (required)", ["", *_REASON_CODES], index=0)
    needs_rationale = action is not None and render.rationale_required(action, rec["action"])
    rationale = st.text_area("Rationale" + (" (required)" if needs_rationale else " (optional)"))
    follow_up = st.text_input("Follow-up (hold only, optional)") if action == "hold" else None

    submit_disabled = action is None or not reason_code
    if st.button("Submit disposition", disabled=submit_disabled):
        resp = httpx.post(
            f"{API_BASE_URL}/api/cases/{case_id}/disposition",
            json={
                "action": action,
                "reason_code": reason_code,
                "rationale": rationale or None,
                "follow_up": follow_up or None,
            },
            timeout=10.0,
        )
        if resp.status_code == 200:
            body = resp.json()
            st.success(f"Case {body['status']} — routed to {body['routed_to']} and recorded.")
        else:
            st.error(resp.json().get("error", {}).get("message", "disposition failed"))

    with st.expander("Audit trail"):
        st.json(_get(f"/api/cases/{case_id}/audit"))


def main() -> None:
    try:
        if "case_id" in st.session_state:
            _case_screen(st.session_state["case_id"])
        else:
            _queue_screen()
    except httpx.HTTPError as exc:
        st.error(f"Cannot reach the API at {API_BASE_URL}: {exc}")


main()
