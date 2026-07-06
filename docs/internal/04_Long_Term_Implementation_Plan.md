# Transaction Fraud Monitoring — Phase 1 Implementation Plan
**Version 1 · Engineering Planning Record**
Lead AI/ML Engineer & Technical Architect
Derived from: *Transaction Fraud Monitoring — Product Specification, Version 1 Design Record (30 June 2026)*

---

## 0. Purpose and how to read this

This document translates the approved specification into an executable engineering plan. It does not revisit product, architectural, Responsible AI, governance, or data decisions. Those are settled.

Every recommendation carries a traceability tag back to the spec: **[FR-n]**, **[NFR-n]**, **[P:principle]**, **[A:component]**, **[DF-n]**, **[§n]**, **[RAI]**. Any behaviour without such a tag is not built.

Where the spec deliberately leaves an implementation detail open (it does so in a few named places), I recommend the simplest option consistent with the approved architecture and mark it as a decision requiring your ratification in Section 14. Those are the only points needing your input before Phase 2.

---

## 1. Spec consistency check (implementability review)

I reviewed the specification for internal inconsistencies or missing information that would block implementation. **The specification is coherent and implementable.** Specifically:

- The pipeline ordering is consistent across §4.3, §4.5, and §5.5: score and rules run independently, then evidence assembly, then deterministic recommendation, then grounded explanation, then the analyst. There is no assembly/recommendation inversion in the document as delivered.
- §5.5 reconciles the one apparent tension a reader might raise: the *logical* dependency (explainer → grounding gate → case view) is fixed, while the *timing* of when generation runs is explicitly deferred to implementation. A recommendation on that timing appears in Section 14; it does not contradict the §4.3 logical order.
- The four architectural layers (ML scorer, deterministic rule engine, LLM explainer, human decision) named in Appendix B map cleanly onto the six logical component kinds in §5.1 (Data, Machine Learning, Deterministic Logic, LLM, Human, Audit). Data and Audit are cross-cutting; the four layers are the runtime composition. Both framings are preserved in the repository structure.

No implementation blocker was found. The open items in Section 14 are deferred details the spec assigns to implementation, not defects.

---

## 2. Implementation strategy

1. **Build the spine first.** The Canonical Evidence Schema (§3, §6.2) is implemented before any layer that consumes it. Every layer imports that schema and never a private shape. This is how the schema principle survives into code rather than becoming an implied convention. **[P:Canonical Evidence Schema][§3]**

2. **Deterministic-first within the explanation layer.** The templated fallback and the grounding gate are built *before* the LLM. Graceful degradation is the floor, not a retrofit. After the explanation milestone, the system must remain fully functional with the LLM disabled at every subsequent milestone. **[P:graceful degradation][FR-12][NFR-2]**

3. **Gates are part of "done," not a later audit.** The simulator-leakage validation (feature-importance, ablation, verdict) and the DF-1 interpretability comparison are inside the scoring milestone. A model that fails the leakage gate is not carried forward, regardless of headline metrics. **[FR-4][FR-26][DF-1]**

4. **Configuration is architecture.** Every governance knob — score-band thresholds, rule parameters, queue-ordering policy — is typed, versioned configuration, never a literal in code, because the spec makes these governance-configurable. **[FR-9][FR-14][§11.2]**

5. **Boundaries are visible in code and on screen.** Score, rule output, generated text, and human decision are distinct types in code and distinct, labelled regions in the UI. The type system enforces the visible-boundaries principle before the UI does. **[P:visible boundaries][NFR-4]**

6. **Online and offline stay separated.** The online path is synchronous request/response. The offline evaluation pipeline is separate, reproducible, and its consumption deferred. The audit log is the only bridge: written by the online path, read by the offline path. **[§5.2][§5.3][FR-21]**

7. **Measured-vs-modelled discipline in every artifact.** Evaluation outputs are labelled *measured* (on synthetic data) or *modelled estimate*. No metric requiring production users or real outcomes is claimed as V1 evidence. **[§7]**

8. **Smallest faithful realization.** Prefer the simplest technology that preserves the architecture: a database-backed queue over a message broker, a server-rendered UI over a heavy client, scikit-learn over exotic models. Where the spec leaves a choice open, take the simplest option consistent with the architecture and record it. **[P:earned complexity]**

**Note on prior assets (execution context, not a design input).** Effort estimates in Section 7 assume familiarity with the stack (FastAPI, a gradient-boosting scorer, threshold selection from a PR curve). That familiarity reduces ramp-up. It does not make any prior system a component of this product: the canonical dataset and schema here are PaySim-based and differ from any earlier work, so the scorer is a fresh PaySim retrain against the interpretable feature substrate, not a port.

---

## 3. Implementation principles (enforceable rules)

- Every implementation decision traces to a spec reference recorded in the code (docstring) and the PR. Untraceable behaviour is not built.
- **No layer collapses.** The ML layer never decides; the policy layer never scores; the LLM never scores or decides; only the human disposes. Enforced by module boundaries and distinct types. **[§5.1][§4.4-A]**
- The grounding gate is deterministic code, never a model. **[FR-11]**
- The audit store is append-only. No UPDATE or DELETE on audit rows. **[FR-20][NFR-3]**
- The disposition control is never pre-selected. This is structural, not a configurable setting. **[FR-15][§4.4-C]**
- Feature computation is point-in-time; splits are out-of-time only. Random splits are prohibited (temporal-leakage guard). **[§6.5][§8.3]**
- Balance-consistency artifact features are treated as suspect and quarantined behind the ablation and leakage gate. They are never silently included in the shipped model without the gate's recorded verdict. **[§6.5][§9][FR-26]**
- Any conflict discovered between implementation and specification stops work and is raised as an implementation concern. It is never silently resolved by changing the design.

---

## 4. Recommended technology stack

The spec is technology-agnostic and §12.8 leaves libraries, frameworks, and deployment open. As Lead Engineer I recommend the following minimal stack. Each choice is the simplest option that preserves the architecture.

| Concern | Recommendation | Rationale (spec-traced) |
|---|---|---|
| Language | Python 3.11+ | One language across pipeline, online path, and evaluation; strong tabular-ML and typing support. |
| Env / deps | `uv` + `pyproject.toml`, locked | Reproducible, fast, shareable by a single developer. **[NFR-5]** |
| Online API | FastAPI + Uvicorn | Synchronous request/response online path with an interactive latency budget. **[§5.2][NFR-1]** |
| UI | Jinja2 + HTMX (server-rendered) | Cleanly expresses separable panels, drill-down, non-pre-selected controls, and labelled AI regions with minimal code. **[FR-14][FR-15][NFR-4][NFR-6]** |
| Persistence | PostgreSQL + SQLAlchemy 2.0 (typed) + Alembic; SQLite for unit tests | Relational store for transactions, cases, dispositions, and the audit log; one data-access layer, SQLite-backed tests keep evaluation reproducible. **[NFR-5][NFR-8]** |
| Triage queue | A database query with a configurable `ORDER BY`, not a broker | The queue is a logical, re-sortable work list over a bounded set of pre-ingested synthetic transactions, not a high-throughput stream. **[FR-14][P:earned complexity]** |
| Scorer | scikit-learn `HistGradientBoostingClassifier` (interpretable primary); LightGBM (kitchen-sink comparator); logistic regression (baseline floor) | Tabular, imbalanced, interpretable; the two-model structure also serves DF-1 and the ablation. **[FR-3][FR-5][DF-1]** |
| Features / calibration | pandas (point-in-time); scikit-learn isotonic/Platt + Brier | Interpretable features over the shared substrate; probability calibration. **[§6.5][FR-23]** |
| Explanation | Provider-abstracted `Explainer` interface; `LLMExplainer` (any hosted instruction-following model); deterministic `GroundingGate`; Jinja2 `TemplatedExplainer` | LLM consumes a constrained evidence set; grounding is a deterministic post-check; provider is swappable and fully optional. The grounding gate plus templated fallback make provider quality non-critical: weak output triggers fallback, not failure. **[FR-10][FR-11][FR-12][NFR-2]** |
| Config | pydantic-settings + versioned YAML (`thresholds`, `rules`, `queue_policy`, `governance`) | Governance knobs are typed, versioned configuration. **[FR-9][FR-14][§11.2]** |
| Logging | structlog (structured), distinct from the audit log | Application logging is separate from the audit record, which is a domain artifact. **[FR-20]** |
| Testing | pytest + Hypothesis (property) + coverage | Property tests for the grounding-gate and policy invariants; golden workflow fixtures. **[FR-11][FR-8]** |
| CI | GitHub Actions | Lint, type-check, test, evaluation smoke-check on every PR. **[NFR-5]** |
| Packaging / deploy | Docker + `docker-compose` (primary, reproducible); optional hosted deploy (Render/Fly.io + managed Postgres) | `docker compose up` reproduces the whole system for judging; hosted deploy is the live demo. **[NFR-5]** |

**Explicitly not recommended for V1, with reasons (removal checked against the spec):**
- **Kafka / Redis / any streaming broker.** The spec requires a synchronous per-case decision loop over a static synthetic dataset, not stream ingestion. NFR-8 requires only that the design not *preclude* higher volume, which a clean data-access layer satisfies. Adding a broker violates earned complexity. **[§5.2][NFR-8][P:earned complexity]**
- **Streamlit for the workspace.** Non-pre-selection, visible boundaries, and drill-down are load-bearing product principles; expressing them in HTML is cleaner than working against Streamlit's widget model. Streamlit remains fine for throwaway evaluation views inside notebooks, not for the case view. **[FR-15][NFR-4]**

React is a sanctioned alternative to Jinja2 + HTMX if a richer client is later wanted; it is not needed to faithfully realize V1.

---

## 5. Repository structure

Structured by architectural layer so implementation follows the architecture. The `schema/` package is the spine every layer imports.

```
transaction-fraud-monitoring/
├── README.md
├── pyproject.toml               # deps (uv-locked)
├── docker-compose.yml           # app + postgres, one-command reproduce
├── Dockerfile
├── .env.example                 # documents required env vars (no secrets)
├── .github/workflows/ci.yml
├── config/                      # governance-configurable knobs (versioned)
│   ├── thresholds.yaml          # score bands → clear/hold/escalate      [FR-9]
│   ├── rules.yaml               # rule parameters                        [FR-6]
│   ├── queue_policy.yaml        # ordering policy, default = risk         [FR-14]
│   └── governance.yaml          # rationale graduation policy            [FR-17]
├── data/                        # gitignored: PaySim raw + prepared
│   ├── raw/
│   └── prepared/
├── src/tfm/
│   ├── schema/                  # Canonical Evidence Schema — the spine   [§3][§6.2]
│   │   ├── entities.py          # Transaction, Account, Counterparty, derived profiles
│   │   └── evidence.py          # assembled Case + groundable evidence set
│   ├── data/                    # Data layer                              [§5.1]
│   │   ├── ingest.py            # PaySim → canonical schema               [FR-1]
│   │   ├── features.py          # point-in-time interpretable features    [§6.5]
│   │   └── splits.py            # out-of-time split                       [§8.3]
│   ├── ml/                      # Machine learning layer
│   │   ├── model.py             # Scorer interface + HistGB impl          [FR-3]
│   │   ├── train.py             # training + candidate comparison
│   │   ├── calibration.py       # probability calibration                 [FR-23]
│   │   └── registry.py          # persisted model + metadata + version
│   ├── rules/                   # Deterministic logic: rule engine        [FR-6]
│   │   ├── engine.py
│   │   └── definitions.py       # velocity, new-benef+large, mule, draining
│   ├── recommendation/          # Deterministic logic: policy             [FR-8][FR-9]
│   │   └── policy.py            # (score band, rule hits) → clear/hold/escalate
│   ├── assembly/                # Evidence assembly                       [FR-2]
│   │   └── assembler.py
│   ├── explanation/             # LLM + grounding + fallback
│   │   ├── explainer.py         # Explainer interface
│   │   ├── templated.py         # deterministic fallback (built first)    [FR-12]
│   │   ├── grounding.py         # grounding gate (deterministic)          [FR-11]
│   │   └── llm_explainer.py     # constrained evidence-scoped prompt      [FR-10]
│   ├── queue/                   # Triage queue ordering                   [FR-14]
│   │   └── ordering.py
│   ├── audit/                   # Audit log (append-only)                 [FR-20][FR-21]
│   │   └── log.py
│   ├── api/                     # FastAPI online path                     [§5.2]
│   │   ├── app.py
│   │   ├── deps.py              # DI: scorer, explainer, session (LLM-off swap)
│   │   └── routes/              # queue, case, disposition, search
│   ├── web/                     # Jinja2 templates + HTMX + static
│   ├── persistence/             # SQLAlchemy models + repositories
│   └── config/                  # typed config loading (pydantic-settings)
├── evaluation/                  # Offline path — reproducible, consumption deferred [§8]
│   ├── model_eval.py            # PR-AUC, precision, recall, ROC-AUC      [FR-22]
│   ├── calibration_report.py    # reliability, Brier, threshold sensitivity [FR-23]
│   ├── grounding_eval.py        # ungrounded rate, fallback rate          [FR-24]
│   ├── subgroup.py              # false-positive-burden by segment        [FR-25]
│   ├── leakage_gate.py          # feature importance + ablation + verdict [FR-26]
│   └── reports/                 # emitted metrics, plots, verdicts
├── notebooks/                   # thin report layer over evaluation/ scripts
├── tests/
│   ├── fixtures/                # scripted workflow cases (QA artifact)   [Addendum A]
│   ├── unit/  integration/  property/
├── migrations/                  # Alembic
└── scripts/
    ├── prepare_data.py
    ├── train_model.py
    └── seed_cases.py            # ingest → score → assemble → recommend → enqueue
```

Layer-to-package mapping: Data → `schema/`, `data/`, `assembly/`; Machine learning → `ml/`; Deterministic logic → `rules/`, `recommendation/`, `explanation/grounding.py`, `explanation/templated.py`, routing (in `api/routes/disposition`); LLM → `explanation/llm_explainer.py`; Human → `web/`, disposition route; Audit → `audit/`. Offline path → `evaluation/` + `notebooks/`.

---

## 6. Milestone plan

Layer-by-layer, in dependency order. Each milestone lists scope, the requirements it satisfies, and its Definition of Done. The **Global Definition of Done** in Section 13 applies to every milestone in addition to the specific DoD below.

**M0 — Project bootstrap** *(Phase 2)*
Repo skeleton, `uv` deps, typed config loading, structured logging, `.env.example`, CI skeleton (lint/type/test), Postgres + Alembic scaffold, docker-compose, project conventions, the audit-writer scaffold.
DoD: `docker compose up` starts the app and database; CI runs on a trivial test; config loads from YAML with a typed schema; conventions documented.

**M1 — Canonical Evidence Schema & data ingestion** *(foundation)*
Entity model (`schema/`); PaySim → canonical ingestion; point-in-time interpretable feature engineering (transaction-intrinsic, account-behavioural, counterparty, balance/sequence families); out-of-time split; persistence models.
Satisfies: **FR-1, §6.2, §6.5, §8.3.**
DoD: PaySim loads into the canonical schema with no loss of the discriminating fields (direction, both-side balances, counterparty); features computed strictly point-in-time (property-tested: no future-row reads); out-of-time split reproducible from a fixed seed and time boundary; downstream code imports only `schema/`.

**M2 — Scoring layer (gated)** *(critical path, heaviest milestone)*
Scorer interface + HistGB; bounded candidate comparison on the out-of-time split; DF-1 interpretable-vs-kitchen-sink comparison with the result recorded; **simulator-leakage gate (feature-importance inspection + ablation with balance-artifact features removed + documented pass/fail verdict)**; probability calibration.
Satisfies: **FR-3, FR-4, FR-5, FR-22, FR-23 (calibration sense), FR-26, DF-1, §9.**
DoD: a selected model that **passes the leakage gate** (a failing model is not eligible and is not carried forward); PR-AUC, precision, recall, ROC-AUC reported on the OOT split and labelled *measured on synthetic*; DF-1 result recorded with the interpretability decision; calibration (reliability + Brier) reported; the ablation delta and the pass/fail verdict recorded alongside the headline metrics.

**M3 — Deterministic rule engine** *(parallel with M2)*
The four V1-demonstrable patterns (velocity spikes; new-beneficiary + large amount; rapid in-and-out mule pass-through; account-draining) as auditable if-then, parameters from `rules.yaml`; extensibility hook; dormant-account reactivation explicitly excluded, documented, no proxy.
Satisfies: **FR-6, FR-7.**
DoD: each rule fires deterministically on constructed fixtures and produces an auditable `RuleHit`; all parameters are configuration; the extension point is demonstrated with a stub; dormant reactivation is documented as out of V1 scope with no proxy carried forward.

**M4 — Evidence assembly** *(depends on M1; integrates M2 + M3)*
Assembler builds the `Case` evidence record answering the seven evidence requirements, push not pull; defines the explicit **groundable evidence set** per case for the grounding gate.
Satisfies: **FR-2.**
DoD: for any transaction, a `Case` is assembled with all seven evidence requirements populated from the canonical schema, plus the score and rule hits as evidence; the groundable set is explicit and complete; assembly runs at ingest (push), verified on fixtures.

**M5 — Recommendation policy** *(critical path; depends on M2 + M3)*
Deterministic mapping (score band + rule hits) → clear/hold/escalate; borderline/low-confidence defaults toward hold; thresholds from `thresholds.yaml`; cost model + sensitivity analysis justifying the defaults.
Satisfies: **FR-8, FR-9, §11.2.**
DoD: the policy is a pure deterministic function, total over every (score band × rule-hit) combination (property-tested); borderline defaults to hold; thresholds are configuration; the recommendation carries its basis and an uncertainty flag; the cost-model justification and sensitivity analysis are documented and labelled *modelled* (not claimed optimal).

**M6 — Explanation: templated + grounding + LLM** *(near-critical; depends on M4)*
Build order enforces graceful degradation: (1) `TemplatedExplainer` (grounded by construction); (2) `GroundingGate` deterministic post-check; (3) `LLMExplainer` with a constrained evidence-scoped prompt; (4) fallback wiring (LLM → gate → pass ? LLM : templated).
Satisfies: **FR-10, FR-11, FR-12, FR-13, FR-24.**
DoD: a templated explanation is always available; LLM output passes through the gate before any human sees it; on grounding failure or LLM unavailability the templated explanation is used; ungrounded-statement rate measured ≈ 0 on held-out synthetic cases with the fallback rate reported; generated text is labelled AI-generated and the synthetic-data disclosure is present.

**M7 — Workspace: triage queue + case view + disposition** *(critical path; depends on M4, M5, M6)*
Triage queue ordered by configurable policy defaulting to risk, ordering basis visible and re-sortable; case view with separable panels, drill-down to raw signals, disposition control **not pre-selected**; disposition (clear/hold/escalate), human sole decider, no auto-execution; rationale capture proportionate; override frictionless and logged; search and filter; in-interface disclosures; routing (escalation carries the assembled case, hold creates a pending state).
Satisfies: **FR-13, FR-14, FR-15, FR-16, FR-17, FR-18, FR-19; NFR-4.**
DoD: the full analyst loop (triage → orient → assess → decide → justify → route) runs end-to-end; the disposition control renders unselected; layer boundaries are visually distinct and AI text is labelled; drill-down returns raw signals; override works and is captured as a signal; search works; routing behaves per spec; no consequential action is auto-executed.

**M8 — Audit log & captured-not-consumed signals** *(cross-cutting; completed after M7)*
The append-only writer (scaffolded in M0, integrated from M4 onward) is completed and verified. Records per case: evidence shown, score, rule hits, recommendation, chosen disposition, rationale, explanation pathway, identity, timestamps. Learning signals captured, not consumed.
Satisfies: **FR-20, FR-21; NFR-3.**
DoD: every disposition writes a complete append-only audit record; a decision is **fully reconstructable from the log alone** (integration-tested); UPDATE/DELETE on audit rows is prevented; signals are captured with no consumption path present.

**M9 — Offline evaluation pipeline (reproducible)** *(consolidation; depends on M2, M5, M6, M1)*
Assembles the offline pipeline: model evaluation (from M2), calibration + threshold sensitivity (from M2/M5), grounding + fallback rates (from M6), subgroup false-positive-burden analysis, and the leakage gate result (from M2) surfaced as a reported gating result. Reproducible scripts with notebook reports; measured-vs-modelled labelling throughout.
Satisfies: **FR-22, FR-23, FR-24, FR-25, FR-26; §7, §8.**
DoD: one command reproduces all offline metrics and artifacts; every result is labelled *measured* or *modelled estimate*; the leakage verdict is reported alongside the headline metrics; subgroup analysis runs as a standing component; nothing in the offline path feeds back into the online path.

**M10 — Integration, latency, hardening, deploy** *(depends on all)*
End-to-end online-path latency measured against the ratified target; graceful degradation verified (LLM disabled → full function); reproducibility check; containerization and demo deploy; disclosure completeness; final traceability audit (every implemented behaviour → FR/principle).
Satisfies: **NFR-1, NFR-2, NFR-5; §7.**
DoD: online-pipeline latency reported and labelled *measured*; the system runs fully with the LLM disabled; `docker compose up` reproduces the running system and seeds demo cases; every FR is implemented or explicitly deferred per the spec, with a traceability table produced.

---

## 7. Dependency graph and critical path

**Dependency graph** (milestone → prerequisites):

```
M0  →  (none)
M1  →  M0
M2  →  M1                     ┐ parallelizable
M3  →  M1                     ┘
M4  →  M1  (integrates M2, M3)
M5  →  M2, M3
M6  →  M4
M7  →  M4, M5, M6
M8  →  produced across M4–M7, verified after M7
M9  →  M2, M5, M6, M1  (consolidation)
M10 →  all
```

**Critical path:** `M0 → M1 → M2 → M5 → M7 → M10`.
A second near-critical chain runs `M0 → M1 → M4 → M6 → M7 → M10`.

The two heaviest milestones, **M2 (scoring + leakage gate + DF-1 + calibration)** and **M6 (explanation + grounding)**, both sit on or adjacent to the critical path. Schedule risk concentrates there.

**Two hard gates, of different kinds:**
- **Simulator-leakage gate (FR-4, FR-26)** is a *project-progression* gate. If the model survives only on balance artifacts, it is ineligible and remediation (feature/model changes, re-run) precedes M5, because the score bands M5 maps have no meaning behind a leaking model. Budget for one remediation cycle.
- **Grounding gate (FR-11)** is a *runtime safety* mechanism, not a progression blocker. Its failure is absorbed by the templated fallback: it blocks an ungrounded LLM claim, never the workflow. The product is functional even if the LLM pathway is never trusted.

**Parallelization:** M2 ∥ M3 after M1; within M6, templated + gate precede the LLM; offline-evaluation components accrete alongside their producing milestones and are consolidated in M9.

---

## 8. Development workflow and branch strategy

- **Trunk-based with short-lived milestone branches.** `main` is protected and always green. Work happens on `milestone/M<n>-<slug>` branches; smaller feature branches fork from the milestone branch and squash-merge back via PR.
- **PRs map to DoD items** and name the FRs/NFRs they satisfy in the description. A PR that cannot cite a requirement is questioned.
- **CI must be green to merge** (Section 10). For a single developer, the discipline is the DoD plus traceability, not heavyweight process; the same structure scales to a small team without change.
- **Tag at each milestone** (`v0.M1`, `v0.M2`, …) for reproducible checkpoints.
- **Conventional commits** for a readable history.

---

## 9. Coding standards

- Python 3.11+, type hints throughout. `mypy` strict on the core layers (`schema`, `rules`, `recommendation`, `explanation/grounding`, `assembly`), enforced in CI.
- `ruff` for format and lint, enforced in CI. No hand-formatting debates.
- Public interfaces carry a docstring citing the FR/principle they implement. Traceability lives in the code, not only in this plan.
- Pydantic v2 for the canonical schema and config; SQLAlchemy 2.0 typed models for persistence; domain and persistence models are mapped explicitly and kept separate.
- Deterministic logic (rules, policy, grounding gate) is written as pure functions with no I/O, so it is trivially property-tested.
- Dependency injection at the API boundary (FastAPI deps) for the scorer, the explainer, and the DB session — this is what makes the LLM-disabled test and provider swaps a configuration change, not a code change.
- Configuration via pydantic-settings; secrets via environment only; `.env.example` documents every required variable. No thresholds, rule parameters, or ordering weights hardcoded.
- Logging is structured and separate from the audit log. The audit record (FR-20) is a domain artifact written to the store, not a log line.

---

## 10. Testing strategy

Layered to match the architecture and weighted toward the risk register (§12.6).

- **Unit tests** per deterministic component: each rule on constructed fixtures; the recommendation policy as a (score-band × rule-hit) truth table including borderline → hold; the grounding gate on grounded and ungrounded inputs; point-in-time feature correctness; PaySim → canonical ingestion.
- **Property tests (Hypothesis)** for invariants where example tests are insufficient:
  - the grounding gate never passes an explanation containing a number or entity absent from the groundable set (the ≈ 0 invariant, expressed as a property) — highest priority;
  - the recommendation policy is total over all inputs and defaults borderline to hold;
  - point-in-time feature computation never reads a future row.
- **Golden / scripted workflow fixtures** (the QA artifact named in Addendum A, strictly excluded from any training or evaluation set): a small hand-authored set — a clean mule pass-through, an account-draining, a new-beneficiary-large, a borderline, a thin-evidence case — each exercising the full online path and asserting the expected recommendation, grounding pass, and correct fallback behaviour.
- **Integration tests:** the online path end-to-end on fixtures (ingest → score → rules → assemble → recommend → explain → disposition → audit); the **LLM-disabled path** asserting full function with the templated explanation (NFR-2); the **audit reconstructability** test rebuilding a decision from the log alone (NFR-3).
- **Evaluation regression (smoke scale) in CI:** the offline pipeline runs on a small sample and asserts the leakage verdict is produced, the grounding rate is computed, and metrics are emitted, so reproducibility (NFR-5) does not silently break.
- **UI checks (lightweight):** endpoint/template assertions that the disposition control renders unselected, AI text carries the label, drill-down endpoints return raw signals, and disclosure banners are present. Full browser automation is out of scope for V1.

Coverage target ≥ 90 % on the core deterministic layers; UI and notebooks exempt. Priority ordering follows the risks: grounding-gate correctness and the leakage gate first, then policy correctness, then point-in-time / out-of-time integrity.

---

## 11. Global Definition of Done

Applied to **every** milestone in addition to its specific DoD:

- Code is typed and lint-clean; `mypy` and `ruff` pass in CI.
- New deterministic logic has unit and, where applicable, property tests, and they pass.
- Every new behaviour cites a spec reference in its docstring and PR.
- No governance parameter (threshold, rule parameter, ordering weight, rationale-graduation rule) is hardcoded; all live in versioned config.
- The system still runs with the LLM disabled (from M6 onward).
- CI is green; the milestone is tagged.
- Any offline-evaluation artifact the milestone produces is reproducible from a single command.

---

## 12. CI/CD expectations

**CI (GitHub Actions, on every PR and on `main`):**
1. `ruff` format-and-lint check.
2. `mypy` type-check (strict on core layers).
3. `pytest` — unit, integration, property — with a coverage gate on the core layers.
4. Evaluation smoke-check (offline pipeline on a small sample).
5. Docker image build; optionally run Alembic migrations against an ephemeral Postgres service.
Merge is blocked on any failure.

**CD:**
- On `main` (or a tagged release), build and publish the image and deploy the demo.
- The primary reproducible artifact is `docker compose up`: it starts the app and Postgres, runs migrations, and seeds demo cases (ingest → score → assemble → recommend → enqueue), so a reviewer reproduces the entire running system with one command. **[NFR-5]**
- The live demo is a single-service hosted deploy (Render or Fly.io) with a managed Postgres.
- The model artifact and config are versioned; the running app loads a pinned model version from the registry.

---

## 13. Deployment strategy

- **Local / judging (primary):** `docker-compose` brings up app + Postgres, migrates, and seeds. Fully reproducible, no external dependencies beyond the container runtime, and it runs with the LLM disabled by default so a reviewer sees the graceful-degradation floor before enabling the LLM.
- **Hosted demo (secondary):** one FastAPI service + managed Postgres on Render or Fly.io. The LLM provider is configured via environment; if unset, the app runs on the templated pathway.
- **Data:** PaySim is prepared offline into the canonical schema; the prepared artifact (or the seed script) ships with the image so the demo is self-contained. Raw PaySim stays gitignored.
- **NFR-8** is satisfied structurally: the data-access layer and the DB-backed queue do not preclude a later move to higher volume; V1 does not target production load.

---

## 14. Implementation concerns (raised separately from design)

These are deferred implementation details the spec assigns to implementation, plus two measurement targets the spec requires but leaves unquantified. **None is a redesign.** Each carries my recommended resolution; I need your ratification on these five before Phase 2, and nothing else.

1. **Explanation generation timing (§5.5, explicitly deferred).**
   *Recommendation:* **on-open generation** for V1. At ingest, run score → rules → assemble → recommend → enqueue (all eager); generate the explanation when a case is opened, then gate it, with the templated fallback bounding open latency. Rationale: most queued synthetic cases will never be opened, so eager generation spends cost on unread cases; on-open aligns cost with consumption; the templated fallback makes any per-open latency spike tolerable. This is consistent with the §4.3 logical order (§5.5 fixes the dependency, not the timing) and is reversible to eager generation without architectural change.

2. **Latency target for NFR-1 (spec says "interactive budget," measured, but sets no number).**
   Since latency is a *measured* V1 metric, a target is needed to measure against.
   *Recommendation to ratify:* the ingest-time pipeline (score → assemble → recommend) completes within a few hundred milliseconds per case on the synthetic set; on-open explanation returns within ~1–3 s with the LLM and effectively instantly on the templated pathway. These are targets to measure and report, not claims.

3. **Rationale graduation policy (FR-17 / Decision D, deferred to governance/implementation).**
   *Recommendation:* the simplest faithful V1 policy — a rationale is required on every disposition (per FR-17), with heavier structured capture triggered on (a) escalate and (b) any override or deviation from the recommendation, the two cases the spec names as most consequential. Encoded in `governance.yaml` so it remains a governance knob.

4. **Bounded model candidate set (FR-3 says "bounded," does not enumerate).**
   *Recommendation:* the candidate set is the interpretable primary (HistGradientBoosting on the curated interpretable features), a kitchen-sink comparator (LightGBM on the fuller feature set, which also supplies the DF-1 comparison and the ablation contrast), and a logistic-regression baseline as a floor. Defensibly bounded; not a redesign.

5. **Confirmation of no blocking inconsistency.**
   I found none. The specification is internally consistent and implementable as written; the pipeline ordering is coherent across §4.3/§4.5/§5.5, and the four-layer and six-kind framings reconcile cleanly. This is recorded here so the review has an explicit statement to sign off.

---

## 15. What Phase 2 will do (preview of what approval unlocks)

On approval of this plan, Phase 2 (Project Bootstrap, M0) creates: the repository structure above; configuration management (typed YAML + pydantic-settings); dependency management (`uv` + locked `pyproject.toml`); the environment strategy (docker-compose app + Postgres, `.env.example`); structured logging; the audit-writer scaffold; the CI skeleton; and the documented project conventions. No architectural-layer logic is implemented in Phase 2. Phase 3 onward implements one layer at a time in the M1→M10 order above, each decision traceable to the specification.

---

*End of Phase 1. Awaiting review and approval before Phase 2.*
