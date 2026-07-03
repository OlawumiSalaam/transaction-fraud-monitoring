"""Streamlit analyst workspace — SCAFFOLD PLACEHOLDER (M0).

This is environment wiring only: it establishes the two-process setup (Streamlit
consuming the FastAPI online path over HTTP) and confirms API reachability. The
actual workspace — triage queue, case view, drill-down, disposition control with
no default selection, labelled AI text — is implemented in M7 per the mandatory
presentation requirements in the Addendum. No workflow behaviour exists here yet.
"""

from __future__ import annotations

import os

import httpx
import streamlit as st

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="Transaction Fraud Monitoring", layout="wide")
st.title("Transaction Fraud Monitoring")
st.caption("Analyst workspace — scaffold placeholder (M0). Workflow implemented in M7.")

st.subheader("Online-path API status")
try:
    resp = httpx.get(f"{API_BASE_URL}/health", timeout=5.0)
    if resp.status_code == 200:
        st.success("API reachable")
        st.json(resp.json())
    else:
        st.error(f"API returned status {resp.status_code}")
except Exception as exc:  # noqa: BLE001 - placeholder health probe
    st.error(f"API not reachable at {API_BASE_URL}: {exc}")
