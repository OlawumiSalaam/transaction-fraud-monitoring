# Transaction Fraud Monitoring — Phase 1.1 Engineering Addendum
**Version 1 · Engineering Boundary Record**
Lead AI/ML Engineer & Technical Architect
Companion to: *Phase 1 Implementation Plan*; derived from the approved *Version 1 Design Record (30 June 2026)*

---

## 0. Purpose and status

This addendum locks the architectural boundaries before implementation begins: the REST API contract, the relational model, the component interface contracts, the implementation risk register, and milestone effort estimates. It adds no product features and revises no design decision.

**Ratification changes recorded from review:**

- **Rationale engagement floor is now an architectural invariant, not a configurable option.** No disposition — including a routine Clear — may be recorded without a minimum of active analyst engagement (at least a structured reason code). A one-click clear is impossible. This has the same status as the prohibition on pre-selected dispositions. The *depth above the floor* (richer structured rationale for Escalate and for overrides/deviations) remains governed by `governance.yaml`. Enforcement is in the Disposition Service and a database `NOT NULL` constraint, never in configuration alone. **[FR-17, elevated][same status as FR-15/§4.4-C]**
- **Presentation layer override: Streamlit for the V1 analyst workspace** in place of Jinja2 + HTMX. Scope decision, presentation layer only; no product requirement relaxed. The online path is exposed through the REST API in §2, and the Streamlit workspace consumes that API. See §1 for the verification result and the mandatory requirements that remain binding.

**Items ratified as proposed (Phase 1, Section 14).** By approving the plan with only the two changes above, the following stand as proposed: on-open explanation generation (item 1); the NFR-1 latency targets to measure against (item 2); the bounded model candidate set — HistGradientBoosting primary, LightGBM comparator, logistic-regression floor (item 4); and the confirmation that no blocking inconsistency exists (item 5). This addendum builds on those.

Phase 2 (M0 Bootstrap) is authorized and scoped. Consistent with the verify-before-proceeding discipline and the stated purpose of this addendum, the boundary contracts below are presented for review before they are scaffolded against in M0.

---

## 1. Streamlit unselected-control verification (requested)

**Result: supported. No implementation concern is triggered.**

- Installed and tested **Streamlit 1.58.0**.
- Both `st.radio(..., index=None)` and `st.selectbox(..., index=None)` render with **no default selection** and return `None` until the analyst actively chooses. Confirmed at source level (the widget's `clearable=(index is None)` empty-state path) and by version: the `index=None` behaviour was introduced in Streamlit **1.27.0**.
- The default of the `index` parameter is `0`, so the no-selection state must be requested **explicitly** with `index=None`. A widget left at its default would pre-select the first option and violate the non-pre-selection invariant. This is a code-review checkpoint, not a version problem.

**Actions:**
- Pin `streamlit>=1.27` (the project will lock the current `1.58.x` via `uv`). Below 1.27 the native mechanism is unavailable.
- Defensive fallback pattern, recorded in case a deployment ever runs an older build: render a sentinel placeholder as the first option (for example `"— select a disposition —"`), treat selection of the sentinel as "no decision," and keep the submit action disabled until a real option is chosen. Not required at 1.58; documented so the invariant is never dependent on an unverified assumption.

---

## 2. API contract (REST)

### 2.1 Architecture placement

The online operational path is exposed through a **service layer** wrapped by a **FastAPI REST API**. The Streamlit workspace consumes this API over HTTP. Keeping the business logic behind the API (rather than importing it into the UI) preserves the layer boundaries and makes the contract testable independently of the presentation layer. *(In-process import of the same service functions is a sanctioned fallback if running two processes proves awkward for the demo; both call identical service operations.)*

### 2.2 Authentication assumptions

- **V1 assumes a single trusted analyst context** over synthetic data. No real authentication or authorization is implemented.
- The actor is identified by an `X-Analyst-Id` request header purely to populate the audit trail's identity field. If absent, a configured default analyst id is used (demo). **[FR-20]**
- Real authentication, authorization, session management, retention, and access control on the audit store are **deployment obligations, deferred**. **[NFR-7]**

### 2.3 Endpoints (each traced to a workflow stage)

| Method & path | Workflow stage | Purpose | Traces |
|---|---|---|---|
| `GET /api/queue` | Triage | Prioritised, re-sortable work queue with visible ordering basis | FR-14 |
| `GET /api/cases/{case_id}` | Orient / Assess | The assembled case: evidence, score, rule hits, recommendation, on-open grounded explanation, disclosures | FR-2, FR-10, FR-11, FR-12, FR-13, FR-15 |
| `GET /api/cases/{case_id}/evidence/{element_id}` | Assess (drill-down) | Raw signal(s) behind a summarised element | FR-15 |
| `POST /api/cases/{case_id}/disposition` | Decide / Justify / Route | Record disposition + rationale, enforce engagement floor, route | FR-16, FR-17, FR-18, FR-20 |
| `GET /api/search` | Cross-cutting | Search / filter over transaction records | FR-19 |
| `GET /api/cases/{case_id}/audit` | Governance | Reconstruct a decision from the log | FR-20, NFR-3 |

### 2.4 Key response schemas (field: type)

```
QueueItem {
  case_id: str, txn_id: str, amount: number, type: str,
  score: number, score_band: "low"|"borderline"|"high",
  recommendation_action: "clear"|"hold"|"escalate",
  recommendation_confidence: "low"|"medium"|"high",
  uncertainty_flag: bool, status: "queued"|"pending"|"cleared"|"escalated",
  queue_priority: number, created_at: datetime
}

QueueResponse { ordering_basis: str, sort_by: str, order: "asc"|"desc", items: [QueueItem] }

Score { probability: number, calibrated: bool, contributing_signals: [ {name: str, value: number, direction: "increases"|"decreases"} ] }

RuleHit { rule_id: str, name: str, fired: true, evidence: {field: value, ...} }

Recommendation {
  action: "clear"|"hold"|"escalate", confidence: "low"|"medium"|"high",
  basis: { score_band: str, rule_ids: [str] }, uncertainty_flag: bool
}

Explanation {
  text: str, pathway: "llm"|"templated", ai_generated: bool,   # ai_generated always true; label shown in UI
  grounding: { verified: true, groundable_fields_used: [str] } # LLM path is only ever returned after passing the gate
}

EvidenceElement {
  element_id: str, label: str, source: "transaction"|"account_history"|"counterparty"|"rule"|"score_signal",
  raw: { ...canonical schema fields... }
}

Case {
  case_id: str, txn_id: str, status: str,
  evidence: { seven_requirements: {...}, elements: [EvidenceElement] },   # FR-2 push
  score: Score, rule_hits: [RuleHit],
  recommendation: Recommendation, explanation: Explanation,
  disclosures: { ai_usage: str, synthetic_data: str },                   # FR-13
  created_at: datetime
}

DispositionRequest {
  action: "clear"|"hold"|"escalate",
  reason_code: str,          # REQUIRED — engagement floor (architectural)
  rationale: str|null,       # REQUIRED when action=="escalate" OR action deviates from recommendation
  follow_up: str|null        # hold only, optional
}

DispositionResponse {
  disposition_id: str, case_id: str, action: str,
  deviated_from_recommendation: bool, routed_to: str,
  status: "cleared"|"pending"|"escalated", recorded_at: datetime
}
```

### 2.5 Error responses

Uniform body: `{ error: { code: str, message: str, details: object|null } }`.

| HTTP | code | Trigger |
|---|---|---|
| 400 | `RATIONALE_FLOOR_REQUIRED` | Disposition submitted without a `reason_code` (engagement-floor violation) |
| 400 | `RATIONALE_REQUIRED_FOR_ACTION` | Escalate, or a deviation from the recommendation, submitted without `rationale` |
| 404 | `NOT_FOUND` | Unknown `case_id` / `element_id` / `txn_id` |
| 409 | `CASE_ALREADY_DISPOSITIONED` | Disposition attempted on a case not in `queued`/`pending`, or invalid transition |
| 422 | `SCHEMA_ERROR` | Malformed request body |
| 500 | `INTERNAL_ERROR` | Unexpected server fault |

**Graceful-degradation contract (explicit):** LLM unavailability, timeout, or grounding failure is **never** surfaced as an error. `GET /api/cases/{case_id}` returns `200` with `explanation.pathway = "templated"`. There is no 5xx path for LLM issues. **[FR-12, NFR-2]**

---

## 3. Database schema (relational)

### 3.1 Mapping to the Canonical Evidence Schema

| Canonical entity (§6.2) | Table(s) |
|---|---|
| Transaction | `transactions` |
| Account | `accounts` |
| Counterparty / beneficiary | `counterparties` |
| Account behavioural profile *(derived)* | computed in features; snapshotted into `cases.evidence` |
| Beneficiary relationship *(derived)* | computed in features; snapshotted into `cases.evidence` |
| Assembled case record | `cases` |
| Rule output | `rule_hits` |
| Human decision | `dispositions` |
| Audit record | `audit_log` |
| Model provenance | `model_versions` |

The derived profiles are not source tables: they are computed point-in-time and snapshotted into `cases.evidence` so the record preserves exactly what the analyst saw (supporting NFR-3 reconstructability). The normalized rows remain the source of truth.

### 3.2 Tables, keys, indexes

```
accounts
  account_id        TEXT PK
  first_seen_step   INT
  is_merchant       BOOL          -- PaySim nameDest 'M' prefix; merchants carry no balance signal

counterparties
  counterparty_id   TEXT PK       -- may reference an account_id (peer) or a merchant id
  is_merchant       BOOL

transactions
  txn_id            TEXT PK
  step              INT NOT NULL              -- PaySim hour index (~744 over 31 days)
  event_ts          TIMESTAMP NOT NULL        -- derived: base_epoch + step hours (enables time-ordering + OOT split)
  type              TEXT NOT NULL             -- PAYMENT|TRANSFER|CASH_OUT|DEBIT|CASH_IN
  amount            NUMERIC NOT NULL
  account_id        TEXT NOT NULL FK -> accounts(account_id)          -- PaySim nameOrig
  counterparty_id   TEXT NOT NULL FK -> counterparties(counterparty_id) -- PaySim nameDest
  direction         TEXT NOT NULL             -- 'outbound' (origin -> dest)
  bal_orig_before   NUMERIC                   -- oldbalanceOrg
  bal_orig_after    NUMERIC                   -- newbalanceOrig
  bal_dest_before   NUMERIC                   -- oldbalanceDest (NULL for merchant dest)
  bal_dest_after    NUMERIC                   -- newbalanceDest (NULL for merchant dest)
  sim_flagged       BOOL                      -- PaySim isFlaggedFraud; ingested, EXCLUDED from features (leakage caution)
  label             BOOL NOT NULL             -- isFraud
  INDEX (account_id, event_ts)   -- account-linked, time-ordered history: the load-bearing structural requirement (§6.2)
  INDEX (counterparty_id)
  INDEX (event_ts)               -- out-of-time split boundary

model_versions
  model_version_id  TEXT PK
  trained_at        TIMESTAMP
  feature_set       TEXT              -- 'interpretable' | 'kitchen_sink'
  metrics           JSONB             -- PR-AUC, precision, recall, ROC-AUC (FR-22)
  calibration       JSONB             -- reliability summary, Brier, method (FR-23)
  leakage_verdict   TEXT              -- 'pass' | 'fail' + ablation delta (FR-26); only 'pass' is eligible (FR-4)
  df1_result        JSONB             -- interpretable-vs-kitchen-sink comparison (DF-1)
  artifact_path     TEXT

cases
  case_id                    TEXT PK
  txn_id                     TEXT NOT NULL UNIQUE FK -> transactions(txn_id)
  model_version_id           TEXT FK -> model_versions(model_version_id)
  score                      NUMERIC NOT NULL          -- calibrated probability
  score_band                 TEXT NOT NULL             -- low|borderline|high (from thresholds.yaml)
  recommendation_action      TEXT NOT NULL             -- clear|hold|escalate (advisory)
  recommendation_confidence  TEXT NOT NULL
  recommendation_basis       JSONB NOT NULL            -- {score_band, rule_ids}
  uncertainty_flag           BOOL NOT NULL
  evidence                   JSONB NOT NULL            -- assembled evidence snapshot = "evidence shown" (FR-2, FR-20)
  explanation_text           TEXT                      -- populated on-open
  explanation_pathway        TEXT                      -- 'llm' | 'templated'
  status                     TEXT NOT NULL             -- queued|pending|cleared|escalated
  queue_priority             NUMERIC NOT NULL          -- from queue_policy.yaml (default: risk)
  created_at                 TIMESTAMP NOT NULL
  INDEX (status, queue_priority)   -- queue ordering (FR-14)
  INDEX (score)

rule_hits
  rule_hit_id   TEXT PK
  case_id       TEXT NOT NULL FK -> cases(case_id)
  rule_id       TEXT NOT NULL             -- velocity|new_benef_large|mule_passthrough|account_draining
  evidence      JSONB NOT NULL            -- the fields that made the rule fire (auditable)
  created_at    TIMESTAMP NOT NULL
  INDEX (case_id)

dispositions
  disposition_id              TEXT PK
  case_id                     TEXT NOT NULL FK -> cases(case_id)
  action                      TEXT NOT NULL             -- clear|hold|escalate
  reason_code                 TEXT NOT NULL             -- ENGAGEMENT FLOOR (architectural; enforced here + in service)
  rationale                   TEXT                      -- required-when-escalate/override (service-enforced)
  deviated_from_recommendation BOOL NOT NULL
  follow_up                   TEXT                      -- hold only
  analyst_id                  TEXT NOT NULL             -- X-Analyst-Id (FR-20)
  created_at                  TIMESTAMP NOT NULL
  INDEX (case_id)

audit_log      -- APPEND-ONLY
  audit_id      TEXT PK
  case_id       TEXT NOT NULL FK -> cases(case_id)
  event_type    TEXT NOT NULL             -- 'case_assembled' | 'explanation_generated' | 'disposition_recorded'
  payload       JSONB NOT NULL            -- full per-case record: evidence shown, score, rule hits,
                                          --   recommendation, disposition, rationale, explanation pathway,
                                          --   identity, timestamps (FR-20)
  created_at    TIMESTAMP NOT NULL
  INDEX (case_id, created_at)
```

### 3.3 Relationships and integrity

- `accounts 1—* transactions`; `counterparties 1—* transactions`; `transactions 1—1 cases`; `cases 1—* rule_hits`; `cases 1—* dispositions` (normally one; history permitted); `cases 1—* audit_log`; `model_versions 1—* cases`.
- **Append-only enforcement on `audit_log`:** `UPDATE`/`DELETE` are revoked at the database role level and the repository exposes insert-only. A decision must be reconstructable from `audit_log` alone. **[FR-20, NFR-3]**
- **Engagement floor at the storage layer:** `dispositions.reason_code NOT NULL`. The Disposition Service additionally rejects empty/whitespace reason codes and enforces `rationale` presence for Escalate and deviations before any write. **[FR-17 elevated]**
- `sim_flagged` is stored for provenance but is excluded from the feature set to avoid trivial simulator leakage. **[§6.5, §9]**

---

## 4. Component interface contracts

Each contract states responsibilities, inputs, outputs, invariants, and — most importantly for boundary preservation — **explicit non-responsibilities**. These are the enforceable boundaries between the six logical component kinds.

**Ingestion** — `data/ingest.py`
- *Responsibilities:* map PaySim rows into the canonical schema; derive `event_ts` from `step`; flag merchant destinations; persist `accounts`, `counterparties`, `transactions`.
- *In:* raw PaySim file. *Out:* canonical rows in the store.
- *Invariants:* no discriminating field (direction, both-side balances, counterparty) is dropped; every transaction has an account and a counterparty; `event_ts` is monotonic in `step`.
- *Not responsible for:* computing features; scoring; any interpretation of fraud.

**Feature Builder** — `data/features.py`
- *Responsibilities:* compute interpretable, behaviourally-grounded features point-in-time (transaction-intrinsic, account-behavioural, counterparty, balance/sequence).
- *In:* canonical transactions + account history up to `event_ts`. *Out:* a feature vector per transaction.
- *Invariants:* uses only information available at `event_ts` (no future rows); the out-of-time split boundary is respected; feature definitions are shared verbatim by scorer, rules, and evidence layers.
- *Not responsible for:* the train/test split policy owner (that is `splits.py`); scoring; deciding.

**Scorer** — `ml/model.py`
- *Responsibilities:* produce a **calibrated probability** and the contributing signals behind it.
- *In:* a feature vector. *Out:* `Score{probability, calibrated, contributing_signals}`.
- *Invariants:* deterministic given inputs and a pinned model version; only a leakage-gate-passing model version is loadable in the online path.
- *Not responsible for:* mapping probability to bands or actions (the policy's job); writing prose; deciding.

**Rule Engine** — `rules/engine.py`
- *Responsibilities:* evaluate the four V1-demonstrable patterns as auditable if-then over the shared feature substrate; parameters from `rules.yaml`.
- *In:* the assembled evidence / feature substrate for a transaction. *Out:* `[RuleHit]` (each carrying the fields that made it fire).
- *Invariants:* pure deterministic function; no probabilistic step; independent of the score (evaluated independently, both preserved as evidence); dormant-reactivation not implemented.
- *Not responsible for:* scoring; recommending; ranking; the queue.

**Evidence Assembler** — `assembly/assembler.py`
- *Responsibilities:* assemble the `Case` evidence record answering the seven evidence requirements (push, not pull); define the explicit **groundable evidence set** for the case.
- *In:* transaction + account history + counterparty + score + rule hits. *Out:* `Case.evidence` + the groundable set.
- *Invariants:* every element traces to a canonical field, a rule hit, or a score signal; the groundable set is complete and is the sole source the LLM may reference.
- *Not responsible for:* scoring; deciding; generating prose; recommending.

**Recommendation Policy** — `recommendation/policy.py`
- *Responsibilities:* map `(score_band, rule_hits) → clear|hold|escalate` with a basis and an uncertainty flag; borderline/low-confidence defaults toward hold; thresholds from `thresholds.yaml`.
- *In:* score band + rule hits. *Out:* `Recommendation`.
- *Invariants:* pure deterministic function, **total** over every (band × rule-hit) combination; advisory only; carries its basis; never overrides a rule or a score silently.
- *Not responsible for:* scoring; generating prose; deciding; executing anything.

**Explainer (interface)** — `explanation/explainer.py`; impls `templated.py`, `llm_explainer.py`
- *Responsibilities:* render assembled evidence into a plain-language risk summary and a draft rationale.
- *In:* `Case.evidence` + the groundable set. *Out:* `Explanation{text, pathway}`.
- *Invariants:* consumes evidence, never sources it; `LLMExplainer` is constrained to the groundable set; `TemplatedExplainer` is deterministic and grounded by construction, always available.
- *Not responsible for:* scoring; deciding; verifying its own grounding (the gate does that); fetching data.

**Grounding Gate** — `explanation/grounding.py`
- *Responsibilities:* verify every number and entity reference in a generated narrative appears in the case's groundable set; on failure, signal fallback.
- *In:* `Explanation` (LLM path) + the groundable set. *Out:* pass, or fail-with-violations.
- *Invariants:* **deterministic code, never a model**; `pass ⟹ every numeric/entity token in the narrative is present in the groundable set (after canonical normalization)`; the templated path bypasses the gate (grounded by construction).
- *Not responsible for:* rewriting or repairing prose (pass/fail only); scoring; deciding.

**Queue Ordering** — `queue/ordering.py`
- *Responsibilities:* order cases by the configurable policy (default: risk); expose the ordering basis; support re-sort.
- *In:* candidate cases + `queue_policy.yaml`. *Out:* ordered cases + the basis.
- *Invariants:* ordering is an operational decision, not a property of the model score; the basis is always visible.
- *Not responsible for:* scoring; deciding; hidden automated routing.

**Disposition Service** — `api/routes/disposition` + service layer
- *Responsibilities:* accept the analyst's disposition; **enforce the engagement floor** (reject any disposition lacking a reason code); enforce the graduation policy (require richer rationale for Escalate and for deviations); compute `deviated_from_recommendation`; perform routing as a state change (clear→cleared, hold→pending, escalate→escalated with the assembled case travelling); trigger the audit write.
- *In:* `DispositionRequest` + analyst identity. *Out:* `DispositionResponse`.
- *Invariants:* a persisted disposition **always** has a non-empty reason code (architectural floor); no consequential/financial action is auto-executed — routing only; overrides are frictionless and never penalised; the disposition is captured as a latent learning signal.
- *Not responsible for:* pre-selecting an action; scoring; generating prose; consuming learning signals.

**Audit Writer** — `audit/log.py`
- *Responsibilities:* write an append-only per-case record (evidence shown, score, rule hits, recommendation, disposition, rationale, explanation pathway, identity, timestamps).
- *In:* the per-case decision record. *Out:* an appended `audit_log` row.
- *Invariants:* append-only (no update/delete); a decision is fully reconstructable from the log alone.
- *Not responsible for:* altering the workflow; deciding; consuming its own records (offline path is deferred).

---

## 5. Implementation risk register (engineering)

Distinct from the product risks in §12.6. Likelihood/Impact on Low/Medium/High.

| ID | Risk | L | I | Mitigation | Surfaces at |
|---|---|---|---|---|---|
| R1 | PaySim field-mapping surprises (merchant `M`-prefixed destinations carry no balance; `isFlaggedFraud` vs `isFraud`; fraud only in TRANSFER/CASH_OUT) corrupt the canonical mapping | M | H | Schema-check + assertions in ingestion; validate on a sample; nullable dest balances for merchants; exclude `sim_flagged` from features; fixtures | M1 |
| R2 | Accidental temporal / point-in-time leakage (rolling windows peeking forward) inflates metrics | M | H | Point-in-time computation; out-of-time split only; property test "features never read a future row" | M1–M2 |
| R3 | Simulator-leakage gate fails (model rides balance artifacts), forcing a remediation cycle on the critical path | M-H | H | Build the ablation harness early; curate interpretable features; budget one remediation cycle before M5 | M2 |
| R4 | Grounding-gate token mismatches ("$1,000" vs "1000", rounding, entity-name variants) cause false rejects/accepts | M-H | M | Canonical numeric/entity normalization before comparison; single rendering path; property + golden tests; measure fallback rate | M6 |
| R5 | LLM emits plausible-but-ungrounded tokens (amounts, dates, names) | H | M* | Constrained evidence-scoped prompt; strict gate; templated fallback (*impact bounded by fallback) | M6 |
| R6 | Streamlit rerun/state handling loses in-progress disposition or drill-down state | M | M | `st.session_state` discipline; API-driven reads/writes; keep logic out of the UI | M7 |
| R7 | A deployed Streamlit build cannot render a genuinely unselected control | L | H | Verified supported at 1.58 (§1); pin `>=1.27`; sentinel-placeholder fallback with disabled submit | M7 |
| R8 | Engagement floor implemented as config-only and drifts to a weak default | L-M | M | Enforce in Disposition Service + `reason_code NOT NULL`; config tunes only depth above the floor; test that a floor-less disposition is rejected | M5/M7/M8 |
| R9 | Audit append-only not truly enforced (ORM permits update/delete) | M | H | DB-role revoke of UPDATE/DELETE; insert-only repository; reconstructability integration test | M8 |
| R10 | On-open explanation latency spikes hurt interactivity when the LLM is slow | M | M | Timeout → templated fallback; measure open latency; optional pre-generation later | M6/M10 |
| R11 | Two-process (FastAPI + Streamlit) local orchestration friction for the demo | L-M | L-M | `docker-compose` both services; sanctioned in-process service-layer fallback | M0/M10 |
| R12 | Reproducibility drift (unpinned deps, non-deterministic training seed) | M | M | `uv` lockfile; fixed seeds; scripted pipeline; CI smoke-check | M0/M2/M9 |
| R13 | Config schema drift (YAML out of sync with code expectations) | M | M | Typed pydantic-settings validation at startup; fail fast | M0/M5 |
| R14 | Calibration instability on synthetic data (isotonic overfits small folds) | L-M | M | Cross-validated calibration; Brier check; choose isotonic vs Platt by measured reliability | M2 |

---

## 6. Milestone effort estimates

One experienced developer, full-time. **Estimates are planning aids, not commitments.** Ranges reflect the risk in each milestone.

| Milestone | Estimate (dev-days) | On critical path | Parallelizable with |
|---|---|---|---|
| M0 Bootstrap | 1.0 – 1.5 | yes | — |
| M1 Schema, ingestion, features, split | 2.5 – 3.5 | yes | — |
| M2 Scoring + leakage gate + DF-1 + calibration *(Fraud Intelligence Engine)* | 3.0 – 5.0 | **yes (heaviest)** | M3 |
| M3 Rule engine | 1.5 – 2.0 | no | M2 |
| M4 Evidence assembly | 1.5 – 2.5 | yes | — |
| M5 Recommendation policy + cost model + sensitivity | 1.5 – 2.0 | yes | — |
| M6 Explanation: templated + gate + LLM + fallback *(Grounded Explanation Layer)* | 3.0 – 4.5 | **near-critical (2nd heaviest)** | — |
| M7 Workspace (Streamlit) | 2.5 – 4.0 | yes | — |
| M8 Audit + reconstructability | 1.5 – 2.0 | no (cross-cutting) | M4–M7 |
| M9 Offline evaluation consolidation | 1.5 – 2.5 | no | accrues across M2/M6 |
| M10 Integration, latency, hardening, deploy | 1.5 – 2.5 | yes | — |

**Totals.** Sequential midpoints ≈ **22–34 dev-days**. With M2 ∥ M3 and the offline-evaluation components accreting inside M2/M6, effective effort is ≈ **20–30 dev-days**, i.e. roughly **four to six weeks** for one experienced developer to faithfully realize the full V1. This is well beyond the hackathon submission window; the estimate is stated honestly rather than compressed.

**Critical path:** `M0 → M1 → M2 → M5 → M7 → M10`, with `M0 → M1 → M4 → M6 → M7 → M10` running close behind.

**Parallel-work opportunities:** M2 ∥ M3 after M1; within M6 the templated explainer and grounding gate precede the LLM; M8's writer is scaffolded in M0 and integrated as M4–M7 produce auditable artifacts; M9 is consolidation of outputs already produced in M2 and M6.

**Highest schedule risk:** **M2** (a leakage-gate failure triggers a remediation cycle that blocks M5) and **M6** (grounding-gate correctness, R4/R5). These two determine the technical credibility of the system.

**Prioritization under schedule pressure (per direction).** Because the offline-evaluation outputs are the strongest V1 evidence (§7), complete the credibility core first: **M1 → M2 (with its gate) → M4 → M5 → M6**, plus the quick **M3** (rules) and **M8** (audit), then **M9** to surface the reported results. The **M7 Streamlit workspace is comparatively predictable** and is the right place to absorb schedule pressure, kept minimal but faithful to the mandatory presentation requirements in §1. No approved feature is dropped; sequencing shifts.

**Validation points (go/no-go gates):**
- *After M1:* schema-check passes; point-in-time property tests pass; the out-of-time split is reproducible.
- *After M2:* leakage-gate verdict is **pass** (a fail blocks progression and triggers remediation); model metrics and calibration reported and labelled *measured on synthetic*.
- *After M6:* ungrounded-statement rate measured **≈ 0** on held-out cases; fallback rate reported.
- *After M7:* cognitive walkthrough against the seven evidence requirements; disposition control renders unselected; full LLM-disabled run passes.
- *After M8:* a decision is reconstructed from the audit log alone.
- *After M10:* online-pipeline latency measured against the ratified targets; full graceful-degradation run; `docker compose up` reproduces the system.

---

*End of Phase 1.1. Boundary contracts presented for review. Phase 2 (M0 Bootstrap) is authorized, scoped, and ready to execute on confirmation.*
