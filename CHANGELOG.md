# Changelog

All notable changes to the Transaction Fraud Monitoring platform are documented in this
file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] — 2026-07-13

The first release: a complete, governance-first, human-in-the-loop decision-support
platform for transaction fraud analysts.

Version 1 delivers the full analyst loop — triage queue → case → assembled evidence →
advisory recommendation → grounded explanation → disposition with mandatory rationale →
routing → append-only audit → exact reconstruction — running end to end on synthetic
PaySim data.

**The headline is not a model metric.** During development the machine-learning scorer
failed the project's simulator-leakage gate and was **excluded from the operational
path**. The product ships with that exclusion documented rather than hidden, and it
continues to operate on deterministic rule evidence. See *Known limitations* below and
[`docs/V1_RETROSPECTIVE.md`](docs/V1_RETROSPECTIVE.md) for the full account.

### Added

**Canonical schema and data foundation**
- A single Canonical Evidence Schema (`schema/`) that every component operates on —
  ingestion, features, rules, scorer, assembler, explainer, workspace, and audit.
- PaySim ingestion into canonical accounts, counterparties, and transactions; idempotent.
- Interpretable, strictly point-in-time feature engineering, property-tested so that no
  feature can read a future row.
- Out-of-time splits only; random train/test splits are prohibited by design.

**Machine learning and the leakage gate**
- A `Scorer` interface with a bounded three-candidate comparison (interpretable
  histogram-gradient-boosting primary, LightGBM "kitchen-sink" comparator, logistic
  floor).
- Probability calibration selected on validation Brier score.
- **A simulator-leakage gate** (`evaluation/leakage_gate.py`) — permutation importance,
  ablation, and a recorded verdict with a human-readable rationale — that gates model
  eligibility. A model that fails it is excluded from operation, regardless of its
  headline metrics.

**Deterministic rule engine**
- An auditable if-then rule engine over the shared feature substrate: `account_draining`,
  `velocity`, and `new_beneficiary_large`. Each firing produces a `RuleHit` carrying the
  exact fields and thresholds that made it fire.
- Rules are provably independent of the ML score.

**Evidence assembly**
- An assembler that builds the case `EvidencePackage` and defines the explicit
  **groundable set** — the only evidence a generated explanation may cite.
- Seven defined evidence requirements answered with named sources, including an honest
  representation of *absence*: an explicit no-baseline element for first-observed
  accounts, and a score-exclusion element carrying the reason but no probability.

**Recommendation policy**
- A pure, deterministic, **advisory** policy mapping evidence to `clear` / `hold` /
  `escalate`, with an absent-score operational path and a present-score path held ready.
- On the absent-score path the policy **never returns `clear`** — with no trustworthy
  score, the system may raise concern but must not certify a transaction as safe.

**Explanation and grounding**
- A templated explainer that is grounded by construction: every sentence derives from a
  named groundable evidence element.
- **A deterministic grounding gate** — never a model — that verifies every number and
  entity in a generated narrative against the case's groundable evidence. Numbers are
  checked after canonical normalisation; entity, rule, and type tokens are checked by
  masking. No ungrounded explanation reaches an analyst.
- An `LLMExplainer` behind the same interface as a documented stub, exercising and proving
  the graceful-degradation path.

**Analyst workspace**
- A Streamlit workspace over a FastAPI service: prioritised re-sortable queue, case
  investigation, evidence drill-down from summary indicator to raw signal, advisory
  recommendation with its basis, labelled AI-generated explanation, disposition, and
  routing.
- The disposition control renders with **no default selection**. Every disposition
  requires a structured reason code — there is no one-click clear — and escalations or
  deviations from the recommendation require a fuller rationale.

**Audit and reconstructability**
- An append-only audit log (no UPDATE, no DELETE), enforced at the application writer, by
  a PostgreSQL trigger, and by database-role revocation in production.
- A complete, versioned, immutable decision snapshot written at disposition, capturing the
  *rendered* artifacts — what the analyst actually saw.
- Decision reconstruction by **pure deserialization** from a single audit row: no
  recomputation, no dependence on current configuration or business logic. A decision made
  today reconstructs exactly, even if the decision logic changes tomorrow.

**Governance**
- All governance parameters — thresholds, rule parameters, queue ordering, rationale depth
  — held in versioned configuration under `config/`, never as literals in business logic.
  Invalid configuration fails application startup.

**Evaluation**
- A reproducible one-command offline evaluation package (`python -m evaluation.run_all`)
  that consolidates model metrics, the leakage verdict, calibration, and grounding
  integrity, labelling every number *measured* or *modelled estimate*.
- `evaluation_manifest.json` as the single source of truth for packaging.

**Deployment**
- Local SQLite path, `docker compose up` (PostgreSQL + migrations + idempotent seed + API
  + workspace), and a live public deployment on Render (API) and Streamlit Community Cloud
  (workspace).

**Engineering**
- 249 passing tests, including Hypothesis property tests for the point-in-time,
  never-clear-without-a-score, policy-totality, and grounding invariants; an end-to-end
  integration test over the real application with the LLM disabled.
- Fully typed (`mypy --strict`), lint-clean (Ruff), with CI covering quality, migration
  up/down, and Docker build.

### Known limitations

- **The ML scorer is excluded from operation.** It fails the simulator-leakage gate; the
  committed manifest records `leakage_verdict: "fail"` and `scorer_eligible: false`. The
  operational path runs on deterministic rule evidence. This is honest degradation, not a
  defect — but it is a degraded mode, not the intended one.
- **The dataset could not support the product's core premise.** Approximately 99.85% of
  PaySim origin accounts appear only once, so the per-account behavioural history the
  product is designed around barely exists in the data. This caps the behavioural ceiling
  of any model on this data at roughly PR-AUC 0.34.
- **No `clear` recommendation is reachable** while the scorer is excluded.
- **The LLM explanation pathway is a stub**; the templated floor ships.
- **Dormant-account reactivation (FR-7) is out of scope** — the data cannot validate it and
  no proxy is carried forward. The `mule_passthrough` rule is defined but not enabled,
  pending the inbound-leg peer evidence it requires.
- **Not production-hardened.** Authentication, authorisation, retention, full-text search,
  per-stage audit events, subgroup/false-positive-burden analysis, and database-level
  append-only enforcement are documented and deferred, with backlog references in
  `docs/internal/TRACEABILITY.md`.

### Notes

- All data is **synthetic** (PaySim). No real, confidential, or customer-identifiable
  information is present, and every case screen discloses this.
- All reported model performance is a **modelled estimate on synthetic data**, not a
  production result, and is attached to a model that is ineligible for operation. No claim
  of real-world fraud-detection performance is made.
- The product makes **no automated operational decisions** — no blocking, no denial, no
  account suspension. This is a permanent design boundary.

[1.0.0]: https://github.com/OlawumiSalaam/transaction-fraud-monitoring/releases/tag/v1.0.0
