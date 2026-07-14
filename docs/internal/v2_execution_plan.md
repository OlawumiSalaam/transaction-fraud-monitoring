# Transaction Fraud Monitoring — Version 2 Execution Plan

## The governing question

Before any task in this plan is started, answer one question:

> **What specific limitation of V1 does this address?**

If the answer isn't clear and specific, the task belongs in a later version. This rule governs every phase below. V2 is about *strengthening* the existing product, not expanding its scope.

**V1's limitations, stated plainly** — these are what V2 exists to address:


1. The ML scorer was excluded from operation — and the reason indicts the dataset, not the model. The chronology matters:

- The baseline model scored PR-AUC 0.9983 (calibrated; measured on synthetic PaySim, out-of-time split). The leakage gate returned FAIL: balance-artifact features held 98.5% of total permutation importance, and ablating them collapsed performance to 0.3365 — an ablation delta of 0.6626.
- Remediation cycle 1 quarantined the balance artifacts and succeeded: artifact importance fell to 0.0%, ablation delta to exactly 0.0. The leak was completely removed.
- The remediated model failed anyway, on a different criterion: behavioural-only PR-AUC of 0.3369 against the 0.50 decision-support floor. Three new behavioural features moved honest performance by 0.0004 over the baseline's ablated result (0.3365 → 0.3369) and carried permutation importances of 0.0003, 0.00002, and 0.00002.

The leak was not hiding a weak model. It was hiding an empty room. Once the artifacts were removed there was almost nothing underneath — because the behavioural signal the product depends on barely exists in the data.

2. The dataset could not support the product's core premise. ~99.85% of PaySim origin accounts appear exactly once. Per-account behavioural history — "is this abnormal for this account" — is the thing the product is built around, and it barely exists. The behavioural ceiling on this dataset is roughly PR-AUC 0.34, and that is a statement about the data, not about the modelling.

3. Consequently, the operational path runs on deterministic rules alone. This is honest and it works — but it is a degraded mode, not the intended one. The system cannot recommend clear, because clearing certifies safety and there is no trustworthy signal with which to certify it.

All figures sourced from the committed artifacts under evaluation/reports/ — tfm-scorer-20260703224313_training_report.json and tfm-scorer-20260704053632_training_report.json. Measured on synthetic data.
Everything in Priority 1 exists to fix (1) and (2) — and note that (1) is caused by (2). Replace the dataset and the model problem is addressable; keep the dataset and no amount of modelling effort will help. Everything else is secondary.

---

## Definition of Done

A milestone is considered complete only when all of the following are satisfied:

- Product objectives achieved.
- Acceptance criteria satisfied.
- Tests implemented and passing.
- **Invariants enforced by tests that fail if violated** — not merely covered. Every new guarantee (point-in-time correctness on a new traversal, the reactivated present-score path, grounding constraints) needs a test that *breaks* when the guarantee is broken.
- Documentation updated.
- Architecture diagram updated where necessary.
- Evaluation artifacts reproduced where applicable.
- Code reviewed.
- Deployment verified where applicable.

**Implementation alone does not constitute completion.**

---

## Milestone Dependencies

```
Phase 0
   │
   ▼
M11 ───────────────┐
   │               │
   ▼               │
M12               Documentation
   │
   ▼
M13
   │
   ├──────────────┐
   ▼              ▼
M14             M15
   │              │
   └──────┬───────┘
          ▼
         M16
```

Each milestone assumes the successful completion of its dependencies unless explicitly stated otherwise.

**Note on the critical path.** M11 and M12 are strictly sequential and every other milestone waits on them. This means **the M11 dataset gate is the plan's single point of failure**: if no candidate dataset passes the leakage gate and the account-recurrence check, M12 cannot proceed as designed and the downstream chain stalls.

That outcome is not a failure of the plan — it is itself a finding. If no available dataset can support genuine behavioural fraud detection without simulator artifacts, the honest response is another **documented exclusion**, not a softened gate. The gate does not bend to keep the roadmap moving. This is the discipline that made V1 credible, and it is the first thing that would be lost under schedule pressure.

---

## Phase 0 — Stabilise V1

**Objective**

Freeze a baseline you can always return to.

**Estimated Duration**

1–2 days

**Dependencies**

- V1 submitted and complete
- All V1 milestones merged to `main`

**Success Criteria**

- `main` verified to contain all V1 work (M4–M10 present) *before* tagging.
- Release tagged `v1.0.0` and pushed.
- `develop` branch created from the tagged release and pushed.
- Hackathon artifacts archived (slides, evaluation reports, submission documentation).
- GitHub Project created for V2 tracking.
- `CHANGELOG.md` created.
- `PROJECT_CONTEXT.md` written — the authoritative description of the current system, so a fresh session or collaborator can orient without re-deriving it.
- `V1_RETROSPECTIVE.md` written.

**Tasks**

- Verify `main` is complete, then tag `v1.0.0`.
- Create `develop`; `main` stays at the stable V1 release.
- Archive hackathon artifacts.
- Create the GitHub Project.
- Write `CHANGELOG.md`, `PROJECT_CONTEXT.md`, `V1_RETROSPECTIVE.md`.

**On the retrospective:** write it as a portfolio artifact, not internal housekeeping. It should tell the engineering story — the leakage discovery, why the model was excluded, how governance absorbed the failure, what the dataset couldn't demonstrate, and what V2 changes. This document is the thing you point people at.

**Deliverable**

A stable, tagged baseline; a clean `develop` branch; a retrospective worth reading; a project-context document that lets anyone (including a future you) pick this up cold.

---

## Phase 1 — Data Foundation (M11) · **PRIORITY 1**

**Objective**

Replace PaySim as the modelling dataset with data that can genuinely support behavioural fraud detection.

**Estimated Duration**

2–3 weeks

**Dependencies**

- Phase 0 completed
- Version 1 frozen (`v1.0.0`)
- Existing leakage-gate instrumentation available and reusable

**Success Criteria**

- A modelling dataset has been selected using **both** documentary evaluation and empirical validation.
- The selected dataset passes the **account-recurrence assessment** (sufficient per-account history exists to support behavioural features).
- The selected dataset passes the **leakage gate** (permutation importance + ablation, ablation delta as primary determinant).
- A Dataset Decision Record (DDR-02) has been written and approved, including the empirical gate results — not merely the argument for selection.
- A publication-quality EDA notebook has been completed.
- The production feature-engineering pipeline has been updated, with point-in-time correctness property-tested per distinct traversal mechanism.

### The gate that governs this phase

**No dataset is selected on paper.** This is V1's hardest-won lesson: PaySim looked structurally ideal (accounts, balances, counterparties, labels, direction) and would have scored well on any comparison matrix. Its fatal properties — the cancellation leak and the single-account structure — only surfaced when the data was *trained on and interrogated*.

So the acceptance criterion for any candidate dataset is empirical, not documentary:

> **A dataset is not selected until it has passed the V1 instrumentation: the leakage gate (permutation importance + ablation) and an account-recurrence check.**

Reuse the existing gate code. It is the most valuable asset V1 produced, and it now becomes a *dataset selection tool*, not just a model check.

### 1.1 — Candidate evaluation (documentary screen)

Evaluate at least five datasets:

- **IBM AML / TabFormer** (24M+ transactions, 2,000 users, genuine multi-year per-account history)
- **IEEE-CIS Fraud Detection** (real Vesta data, real labels, card-linked entity structure)
- **Sparkov / Kartik2112** (1.85M transactions, 1,000 customers, 800 merchants, clear-text features)
- **BankSim** (retained for comparison; likely dominated by Sparkov)
- **CaixaBank Tech 2024** (per-account history + interpretable features + real transaction base)
- *(Optional)* Fraud Detection Handbook datasets

Compare on:

- behavioural richness (does per-account history actually exist?)
- **account recurrence** (what % of accounts appear more than once? This is the V1-specific check — PaySim scored ~0.15%)
- leakage risk (synthetic generator artifacts; known documented issues)
- feature interpretability (can rules and explanations operate on these fields?)
- fraud labels (real vs injected; base rate)
- temporal structure (can point-in-time features be computed?)
- operational realism (does the fraud typology resemble what a real team sees?)
- entity-model compatibility (how much of V1's schema survives?)

**Deliverable:** `docs/Dataset_Evaluation.md` with the comparison matrix.

### 1.2 — Empirical screen (the gate)

Take the **top two** candidates from the documentary screen and run them through the instrumentation *before* committing to either:

- Compute account recurrence directly. If most accounts appear once, the dataset cannot support the product — reject regardless of how good it looks otherwise.
- Train a quick baseline scorer and run the **leakage gate**: permutation importance, ablation, verdict.
- Check for generator artifacts: does any single feature or feature family carry implausible importance?

**Deliverable:** `docs/Dataset_Gate_Results.md` — the empirical evidence for the selection, not the argument for it.

### 1.3 — Selection and decision record

Choose one:

- **Replace PaySim** (most likely; preferred if a candidate passes cleanly)
- **Combine datasets** (only with a strong reason — a single canonical schema is a V1 architectural principle and should not be broken lightly)
- **PaySim for demo, new dataset for modelling** (viable, but creates two schemas; document the cost)

Write a Dataset Decision Record (DDR-02) in the style of DDR-01: the recommendation, the reasoning, the rejected alternatives, the trade-offs, and — critically — the *empirical gate results* that justify it.

**Note on the entity model:** the leading candidates (IEEE-CIS, TabFormer, Sparkov, CaixaBank) are card/merchant-based, not peer-account-transfer-based. Adopting one means re-modelling the canonical schema from peer-account transfers to customer-card-merchant transactions, and re-deriving the rules around card-fraud typologies (stolen cards, card testing, geographic anomalies) rather than account draining and mule chains. **Budget for this explicitly.** It is the real cost of Phase 1 and it cascades into M12 and M13.

### 1.4 — Exploratory data analysis

**Deliverable:** `notebooks/01_data_understanding.ipynb` — publication quality. Establish the dataset's structure, distributions, temporal properties, class balance, account recurrence, and — explicitly — its limitations. Descriptive only; no feature engineering, no modelling.

### 1.5 — Feature engineering

**Deliverable:** `notebooks/02_feature_engineering.ipynb` + the production feature pipeline.

Build the behavioural substrate V1 could not:

- **Account history**: baseline spend, transaction cadence, dormancy, recency
- **Temporal features**: velocity windows, time-since-last, hour/day patterns, seasonality
- **Counterparty/merchant features**: new-vs-known, concentration, category deviation
- **Behavioural deviation**: amount relative to this account's own history, category deviation, geographic deviation where available

**Carry forward from V1, non-negotiable:**

- Point-in-time correctness, enforced by property tests, **per distinct traversal mechanism** (V1's IMP-005 rule: any new history-dependent feature either reuses a verified traversal or brings its own invariant-level test).
- Out-of-time splits only. No random splits, ever.
- Interpretable features only — the rule engine and explanation layer must be able to operate on them, and a human must be able to read them.

---

## Phase 2 — Model Redevelopment (M12) · **PRIORITY 1**

**Objective**

Build a scorer that passes the leakage gate and is fit for operational deployment.

**Estimated Duration**

2–3 weeks

**Dependencies**

- M11 completed
- A dataset selected and gate-passed
- Feature pipeline in place with point-in-time correctness tested

**Success Criteria**

- Five candidate models trained, each answering a *distinct, pre-registered question*.
- Full evaluation protocol executed: PR-AUC (primary), ROC-AUC, precision/recall, calibration, explainability, cost.
- Preprocessing fit on the training fold only; the test split touched exactly once.
- **The selected model passes the leakage gate**, with the ablation delta as the primary determinant.
- Calibration selected on validation Brier score (never on test).
- Operational thresholds defined as a governance decision with a transparent cost rationale, held in versioned config — never a code literal.
- Model card updated; the trained, gated, calibrated artifact produced.

### 2.1 — Candidate models

Train and compare five, each with a defined role so the comparison produces *information*, not just five numbers:

| Model | Role in the comparison |
|---|---|
| **Logistic Regression** | Interpretable floor. If the tree models can't beat this meaningfully, the features are the problem, not the model. |
| **Random Forest** | Bagging baseline; variance-reduction contrast to the boosting family. |
| **XGBoost** | Boosting reference; the field's default, so its absence would be questioned. |
| **LightGBM** | Speed/scale contrast; the natural *kitchen-sink* comparator for the interpretability trade-off study (DF-1). |
| **CatBoost** | Categorical-native. Genuinely differentiated if the new dataset is categorical-heavy (merchant, category, card type) — which the leading candidates are. |

**The rule that keeps this honest:** each model must answer a question the others don't. If two models are answering the same question, one of them is padding. **Write down the question each model answers before training it.**

### 2.2 — Evaluation protocol

Compare on:

- **PR-AUC** (primary — class imbalance makes ROC-AUC flattering)
- ROC-AUC (secondary, reported for comparability)
- Precision / Recall at operational thresholds
- **Calibration** (reliability curve + Brier score)
- **Explainability** (feature-importance stability; SHAP feasibility)
- Training / inference cost

**Protocol discipline, carried from V1:**

- Preprocessing fit on the **training fold only**, never on the full dataset. Imputation and scaling live inside each candidate's pipeline; the canonical feature dataset stays immutable.
- The **test split is touched once**, at final evaluation. Nothing is tuned on it.
- Every metric labelled **measured** vs **modelled estimate**.

### 2.3 — The leakage gate (the phase's real deliverable)

Re-run the full V1 instrumentation on the selected model:

- **Permutation importance** — what is the model actually leaning on?
- **Ablation** — remove the suspect feature family; how much performance survives?
- **Verdict** — the ablation delta is the primary determinant. Strong residual performance may *support* a pass when the delta is small, but may **never rescue** a pass when the delta is large. A model whose performance materially depends on artifact features is ineligible regardless of how well the remainder performs.

**This gate does not flex.** It is what made V1 credible. A V2 model that fails it is excluded exactly as V1's was — and if that happens, the honest outcome is another documented exclusion, not a softened threshold.

### 2.4 — Calibration and thresholds

- Compare isotonic vs sigmoid (Platt) calibration; select on validation Brier score, never on test.
- Define the operational thresholds (clear / hold / escalate) as a **governance decision with a transparent cost rationale for the defaults** — not as an optimisation claiming to find the "correct" operating point. The cost model is a set of stated assumptions; present it as such, with sensitivity analysis.
- Thresholds live in versioned config. **No governance parameter is ever a code literal.**

**Deliverable:** `notebooks/03_model_development.ipynb` + the trained, gated, calibrated model artifact + an updated model card.

---

## Phase 3 — Operational Integration (M13) · **PRIORITY 2**

**Objective**

Put a *validated* scorer back into the operational path.

**Estimated Duration**

1–2 weeks

**Dependencies**

- M12 completed
- A gate-passing, calibrated model artifact exists

**Success Criteria**

- The gated scorer is integrated behind the existing `Scorer` interface; `eligible = true` set only on a gate pass.
- The **present-score path** in the recommendation policy is activated and tested — including the `clear` recommendation, which V1 structurally could not produce.
- Evidence assembly carries the score and its contributing signals.
- Explanations reference the score honestly; per-instance attribution (SHAP) reconsidered now that global-only signals are no longer the constraint.
- Evaluation pipeline and `evaluation_manifest.json` updated.
- **The graceful-degradation path is verified still intact** — the product must still run correctly with the scorer disabled.

This phase is where V1's architecture pays its dividend: the scorer slots back in behind the existing interface, and the recommendation policy's **present-score truth table** — built in V1 as dormant future-ready code — activates. The system was designed for this.

**On the `clear` recommendation:** with a trustworthy score, the system can finally recommend *clear* — which V1 could never do, because clearing certifies safety and V1 had no trustworthy signal to certify it with. This is the single most visible product change in V2.

**Keep the graceful-degradation path intact.** The templated explainer, the honest no-score state, the rules-only operation — none of it is removed. It becomes the fallback rather than the default. The system must still degrade honestly if a future model fails a gate.

**Deliverable:** a working product with a validated, operational scorer — *and* a preserved honest-degradation path.

---

## Phase 4 — Product Enhancement (M14) · **PRIORITY 3**

**Objective**

Improve analyst productivity.

**Estimated Duration**

2–3 weeks

**Dependencies**

- M13 completed (a working product with an operational scorer)

**Success Criteria**

- Each shipped feature has a documented answer to the governing question ("what V1 limitation does this address?").
- Search (transactions, accounts) implemented and tested — closing a named brief requirement V1 only minimally satisfied.
- Pagination, saved filters, and investigation notes shipped.
- Evidence visualisation improved without increasing cognitive load.
- Any dashboard added is an *entry point into a decision*, not an oversight display.

**Tasks**

- **Search** (transactions, accounts) — addresses a named brief requirement V1 only minimally satisfied.
- **Pagination** — addresses queue scale, which V1 never faced with 5 demo cases.
- **Saved filters** — addresses repeat triage workflows.
- **Investigation notes** — addresses case continuity across sessions.
- **Better evidence visualisation** — addresses comprehension speed.
- **Dashboards** — *be careful here.* V1 deliberately rejected "dashboard as the product" in favour of the investigation workspace. Any dashboard added in V2 must be an *entry point into a decision*, not an oversight display that terminates in display. Don't quietly reintroduce the thing you rejected.

**On `mule_passthrough`:** do not activate it here unless the new dataset supports it. V1 deferred it because it needs inbound-leg peer evidence, which PaySim's structure couldn't provide. If the new dataset has genuine account history, revisit it — using the documented activation path from IC-M3-01 (assembler inbound-leg extension + history-aware rule input).

---

## Phase 5 — LLM Enhancement (M15) · **PRIORITY 3**

**Objective**

Improve explanation quality — without weakening the grounding guarantee.

**Estimated Duration**

1–2 weeks

**Dependencies**

- M13 completed
- Groundable-evidence contract intact

**Success Criteria**

- LLM explainer implemented behind the existing `Explainer` interface (single provider).
- **Grounding rate is a measured health metric**, not an asserted property.
- Hallucination testing implemented, with results reported.
- Latency measured for both on-open and eager-generation strategies; the timing decision V1 deferred is now made on data.
- **The templated floor remains the default fallback** and the product remains fully functional with the LLM disabled.

**Tasks**

- Better prompts; single-provider implementation behind the existing `Explainer` interface.
- **Hallucination testing** — the grounding rate becomes a *measured health metric*, not an asserted property.
- Grounding improvements: V1's deterministic gate does **token-level** checking (numbers, entities, rule IDs). Its honest limit is that it catches fabricated *values*, not fabricated *relationships* between real values. V2 can improve this — but be precise about what any improvement actually guarantees, and don't claim claim-level verification a deterministic checker cannot deliver.
- Latency evaluation (on-open generation vs eager pre-computation — the timing decision V1 deliberately deferred).

**The templated floor stays.** It is the reliable default and the graceful-degradation path. The LLM is an enhancement layered on top, never a dependency.

---

## Phase 6 — Production Readiness (M16) · **PRIORITY 4**

**Objective**

Harden the system for real deployment.

**Estimated Duration**

2–3 weeks

**Dependencies**

- M14 and M15 completed

**Success Criteria**

- Authentication and role-based access implemented (analyst / reviewer / admin).
- **Database-level append-only enforcement** on the audit log implemented and tested (V1's BL-M8-01).
- Monitoring in place for model drift, grounding failure rate, override rate, and latency.
- Performance testing completed against defined targets.
- Security review completed.
- The public demo is no longer drainable — replenishment or reset implemented.

**Tasks**

- Authentication and role-based access.
- **Database-level append-only enforcement** on the audit log (V1's BL-M8-01 — the trigger deferred to avoid migration risk near the deadline). This is now the right time.
- Monitoring: model drift, grounding failure rate, override rate, latency.
- Logging improvements; performance testing; security review.
- **Demo robustness**: the live demo's queue is currently *consumable* — cases leave permanently as users disposition them. Add replenishment or a reset mechanism so a public demo can't be drained.

---

## Cross-cutting: Testing

Current: **249 tests.** Target: 350+.

**But frame the target correctly.** V1's tests were valuable because they enforced *specific invariants* — no-recomputation on audit reconstruction, no-pre-selection on the disposition control, point-in-time correctness per traversal mechanism, no-score-in-the-groundable-set. Not because there were 249 of them.

So the target is: **every new invariant is enforced by a test that fails if it's violated.** The count is a byproduct.

New coverage areas: API tests, UI tests, integration tests, end-to-end tests, performance tests — plus invariant tests for every new feature family (point-in-time correctness per new traversal) and for the reactivated present-score path.

---

## Cross-cutting: Documentation & Deployment

**Documentation** — updated continuously, not at the end.

**Deployment** — maintain Streamlit + Render. Add GitHub Actions CI/CD, versioned releases, release notes.

---

## Supporting Documentation

The following documents are maintained alongside the execution plan.

| Document | Purpose |
|---|---|
| `PROJECT_CONTEXT.md` | Authoritative description of the current system |
| `V1_RETROSPECTIVE.md` | Engineering lessons from Version 1 |
| `Dataset_Evaluation.md` | Documentary comparison of candidate datasets |
| `Dataset_Gate_Results.md` | Empirical dataset validation |
| `DDR-02.md` | Dataset selection decision record |
| `V2_PRODUCT_SPECIFICATION.md` | Product requirements and scope |
| `CHANGELOG.md` | Version history |

---

## Priority Order

**Priority 1 — the biggest V1 limitation**
Dataset evaluation → empirical gate → selection → EDA → feature engineering → model redevelopment.
*Why:* V1's dataset could not exercise the product's core premise, and its model could not be trusted. Nothing else in V2 matters as much as fixing this.

**Priority 2 — restore the intended operational mode**
Integrate the validated scorer → activate the present-score policy path (including `clear`) → improve explanations with per-instance attribution.
*Why:* This is what V1 was architecturally built for and never got to demonstrate.

**Priority 3 — analyst experience**
Search, filtering, pagination, notes, evidence visualisation, LLM explanation quality.
*Why:* Real, but it improves a product that already works. Secondary to making the product work as intended.

**Priority 4 — production hardening**
Auth, monitoring, DB-level audit enforcement, performance, security.
*Why:* Necessary for real deployment; not what V2 is fundamentally *for*.

---

## The two rules that carry over from V1

1. **The leakage gate does not flex.** It governs dataset selection *and* model eligibility. A model that fails is excluded and the failure is documented — never a softened threshold. This is what made V1 credible and it is the thing most worth preserving.

2. **The model is not the product.** Even when V2's scorer passes and goes operational, the architecture must still be able to run without it. The honest-degradation path — templated explanations, rules-only recommendation, the transparent no-score state — stays intact as the fallback. The day a future model fails a gate, the product should survive it exactly as V1 did.