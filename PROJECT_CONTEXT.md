# Project Context

**Authoritative orientation document for the Transaction Fraud Monitoring platform, as
implemented in Version 1 (`v1.0.0`).**

This document exists so that a new engineer — or a fresh AI session — can understand the
system as it stands today without reconstructing its history. It describes **only what is
implemented in Version 1**. It does not describe planned Version 2 functionality.

It is deliberately dense and factual. Where a fact needs explanation, it points to
[`docs/PROJECT_DOCUMENTATION.md`](docs/PROJECT_DOCUMENTATION.md) — the full engineering
reference, which explains *why* each decision was made. This document tells you *what is
true*; that one tells you *why*.

Every number below is read verbatim from a committed artifact under `evaluation/reports/`.
All figures were produced on synthetic PaySim data. No real-world performance is claimed.

---

## 1. What this is

**Product purpose.** Fraud analysts do not lack scores. They lack the time and the
defensible basis to turn an alert into a decision they can justify to a manager, an
auditor, or a regulator months later. The bottleneck in transaction fraud monitoring is
not prediction — it is the manual assembly of context and the consistency and
defensibility of the disposition.

**Product vision.** An AI-assisted case-investigation workspace. For each flagged
transaction the system assembles the supporting evidence, evaluates deterministic fraud
rules, produces an advisory recommendation, and generates a plain-language explanation
that is verified against the evidence before an analyst ever sees it. The analyst records
the disposition — always with a structured rationale — and the system writes a complete,
reconstructable audit record.

**The design philosophy, in one line:** *AI supports the decision; it never makes it.*

**The engineering contribution is not a fraud classifier.** It is a governance-first
architecture in which model failure is an observable, handled state. That claim is not
rhetorical: in Version 1 the model *did* fail, it *was* excluded, and the product
continued to operate. Section 2 describes that state.

---

## 2. Current operational state

**This is the first thing to understand about the running system.**

The machine-learning scorer is **excluded from the operational path**. It failed the
simulator-leakage gate and is therefore ineligible under FR-4. The committed manifest
(`evaluation/reports/evaluation_manifest.json`) records this directly:

```json
"model_version_id": "tfm-scorer-20260704053632",
"leakage_verdict": "fail",
"scorer_eligible": false
```

**What this means in practice:**

- The recommendation policy runs on its **absent-score path**: it recommends from
  deterministic rule evidence alone. The score band is `none`.
- The policy **can never return `clear`** while the scorer is excluded. Clearing certifies
  a transaction as safe, and the system has no trustworthy signal with which to certify
  it. It can raise concern; it cannot pronounce safety. An escalating rule yields
  `escalate`; any other fired rule yields `hold`; no rule hits yields `hold` with an
  uncertainty flag.
- The evidence package carries a populated `score_signal` element stating the **exclusion
  reason** but carrying **no probability**. Consequently no score value traces to any
  groundable element, and any explanation asserting a score is *structurally* ungroundable
  (see invariant I-2).
- The case screen displays this to the analyst explicitly — model scoring is excluded by
  the leakage gate, and the case is assessed on verified rule evidence.

**This is honest degradation, not breakage.** Every other layer is fully operational. The
scorer was always one input behind an interface, so its exclusion is a *handled operating
state* rather than a failure of the product. Reintroducing an eligible scorer flips the
score-status flag and activates the dormant present-score path with no change to the
policy or any other layer.

**Why it failed** — the full chronology is in
[`docs/V1_RETROSPECTIVE.md`](docs/V1_RETROSPECTIVE.md). In brief, and traceable to the
committed training reports:

| | Baseline `tfm-scorer-20260703224313` | Selected `tfm-scorer-20260704053632` |
|---|---|---|
| Headline PR-AUC | 0.9983 | 0.3209 |
| Balance-artifact importance share | 98.5% | **0.0%** |
| Ablation PR-AUC delta | 0.6626 | **0.0** |
| Remaining behavioural PR-AUC | 0.3365 | 0.3369 |
| Leakage verdict | FAIL | **FAIL** |

The baseline failed on **leakage**. Remediation quarantined the balance artifacts and
removed the leak completely — importance share to 0.0%, ablation delta to 0.0. The
remediated model then failed on a *different* criterion: behavioural-only PR-AUC of 0.3369
against the 0.50 decision-support floor. **The leak was fixed and there was almost no
behavioural signal underneath it.** That is a finding about the dataset, not the model.

---

## 3. System scope (Version 1)

**In scope and delivered:**

- Ingestion of PaySim into a canonical schema, with point-in-time features and an
  out-of-time split.
- An ML scorer trained and evaluated through a real `Scorer` interface, subject to the
  simulator-leakage gate (which excluded it).
- A deterministic rule engine with auditable rule firings.
- Evidence assembly answering seven defined evidence requirements, with an explicit
  groundable set.
- A deterministic recommendation policy mapping evidence to `clear` / `hold` / `escalate`.
- A templated explainer plus a deterministic grounding gate, with graceful fallback.
- A Streamlit analyst workspace over a FastAPI service.
- An append-only audit log and single-event decision reconstruction.
- A reproducible offline evaluation package.

**Explicitly out of scope:**

- **Automated operational decisions** — no automated blocking, denial, or account
  suspension. This is a permanent design boundary, not a deferral.
- **A production LLM explanation pathway** — the LLM sits behind the real `Explainer`
  interface as a documented stub; the templated floor ships.
- **Dormant-account reactivation detection** (FR-7) — PaySim's typology and thin
  per-account histories cannot validate it; no proxy is carried forward.
- **Streaming ingestion (Kafka) and a caching tier (Redis)** — the architecture places the
  seams; the infrastructure is deliberately omitted.
- **Authentication and authorisation, full-text search, subgroup/false-positive fairness
  analysis, threshold sensitivity analysis** — deferred with backlog references in
  `docs/internal/TRACEABILITY.md`.

---

## 4. The four-layer architecture

The system is organised as layers with strictly separated responsibilities. The central
invariant — enforced in code, not by convention — is **no layer collapse**.

| Layer | Modules | Responsibility | Never does |
|---|---|---|---|
| **ML scorer** | `ml/` | Produce a calibrated probability through the `Scorer` interface | Recommend, explain, decide |
| **Deterministic rules** | `rules/` | Evaluate auditable if-then rules → `RuleHit` evidence | Read the ML score, decide |
| **Explanation** | `explanation/` | Turn evidence + recommendation into prose; verify it against the evidence | Source evidence, score, decide |
| **Human decision** | `web/`, `services/disposition_service.py` | Capture the analyst's disposition and rationale | Auto-execute a decision |

Supporting layers: ingestion and features (`data/`), evidence assembly
(`assembly/assembler.py`), the recommendation policy (`recommendation/policy.py`), queue
ordering (`queue/`), audit (`audit/`), persistence (`persistence/`), orchestration
(`services/`), and the canonical schema spine (`schema/`), which every module imports.

**Why the layers intentionally remain separate.**

This is not tidiness; it is the property the product's credibility rests on, and Version 1
paid it out in full.

- **The scorer predicts; the policy recommends.** Because the recommendation policy
  consumes a *score status* through an interface — never a model object — the scorer could
  be excluded without the policy changing a line. The absent-score path was already there.
- **The rules never read the score.** The rule engine is provably independent of the
  scorer (`tests/unit/test_rules.py::test_engine_evaluate_is_independent_of_score`), so
  the deterministic evidence path survived the model's exclusion intact. This is precisely
  why the product still works.
- **The explanation layer never sources its own evidence.** It may only cite the
  assembler's groundable set. When the scorer was excluded, no score value entered that
  set — so an explanation *cannot* assert a score, by construction rather than by
  discipline.
- **Only the human disposes.** No layer may take the consequential act. That boundary is
  what makes the whole arrangement worth building.

A useful way to read this: **the scorer's exclusion did not cascade.** In a system where
the model *is* the product, that failure is terminal. Here it was an operating state.
Layer separation is the reason.

Full architectural treatment: `docs/PROJECT_DOCUMENTATION.md` §4.

---

## 5. Operational invariants

Each of these is enforced by a test that fails if the invariant is violated. They are not
conventions, and they are not relaxed for convenience.

| # | Invariant | Enforced by |
|---|---|---|
| **I-1** | **No pre-selection on the disposition control.** The control renders with no default; the analyst must actively choose. | `tests/unit/test_workspace.py::test_render_disposition_control_has_no_default` |
| **I-2** | **Groundable evidence contract.** Only the assembler's explicit groundable set may be cited by a generated explanation. No score value traces to any groundable element while the scorer is excluded; the synthetic-data disclosure is display-only and never groundable. | `tests/unit/test_assembler.py::test_no_score_value_traces_to_any_groundable_element`, `::test_disclosure_is_display_only_not_groundable` |
| **I-3** | **Append-only audit with reconstruction by pure deserialization.** The writer exposes `append` and nothing else — no UPDATE, no DELETE. Reconstruction reads one `disposition_recorded` row and deserializes it: it invokes no rule engine, no policy, no explainer, no grounding gate, and no configuration. | `tests/unit/test_audit_writer.py::test_writer_is_append_only`, `tests/unit/test_audit_reconstruct.py` |
| **I-4** | **No governance parameter as a code literal.** Thresholds, rule parameters, queue ordering, and rationale depth live in versioned config under `config/`. Invalid configuration fails startup. | `config/*.yaml`, `tests/unit/test_config.py`, fail-fast lifespan in `api/app.py` |
| **I-5** | **Point-in-time correctness, property-tested per traversal mechanism.** Features for a transaction at time *t* use only data strictly before *t* within the same account. Any new history-dependent traversal brings its own invariant-level test (standing rule IMP-005). | `tests/unit/test_features.py::test_features_point_in_time_invariant` (Hypothesis property test) |

**Further invariants V1 enforces:**

- **The grounding gate is deterministic code, never a model.** No ungrounded explanation
  reaches an analyst. (`explanation/grounding.py`, `tests/unit/test_explanation.py`)
- **The engagement floor.** Every disposition — including a routine clear — requires at
  least a structured reason code. A one-click clear is impossible. Enforced by the
  Disposition Service *and* a database `NOT NULL` constraint. It is deliberately **not**
  configurable and is not represented in `governance.yaml`.
- **`clear` is unavailable on the absent-score path.**
  (`tests/unit/test_recommendation.py::test_absent_score_never_clears` — property test)
- **Out-of-time splits only.** Random train/test splits are prohibited.
  (`data/splits.py`, `tests/unit/test_splits.py`)
- **Graceful degradation.** The product remains fully functional with the LLM disabled. An
  LLM failure never surfaces to the analyst as an error.
- **Layer visibility.** Model outputs, rule outputs, AI-generated text, and human decisions
  are visibly and structurally distinct. Generated text is labelled; synthetic data is
  disclosed.

---

## 6. Governance principles

- **The leakage gate does not flex.** It is the progression criterion for model
  eligibility. A model that fails is excluded and the failure is documented — never a
  softened threshold, never a leaking model presented as production-ready to meet a
  deadline. Version 1 shipped the documented failure.
- **Governance is architecture, not documentation.** Its parameters are versioned config;
  its invariants are enforced in code and in the database.
- **Honest reporting.** Every reported number is labelled *measured* or *modelled
  estimate*. Synthetic data is disclosed wherever it is used.
- **Thresholds are a governance decision, not an optimisation.** The numeric gate
  thresholds are configurable **decision-support defaults**; they support the verdict but
  do not define it. The full evidence and a human-readable rationale are always recorded,
  so a reviewer may disagree with a default without the gate silently flipping.

**Governance configuration (`config/`):**

| File | Holds |
|---|---|
| `thresholds.yaml` | Score bands (`low_max: 0.30`, `high_min: 0.80`); escalating rules (`account_draining`) |
| `rules.yaml` | Rule parameters (e.g. `min_fraction_of_balance: 0.9`, `window_hours: 24`, `amount_threshold: 200000`) |
| `model.yaml` | Seed (42), split boundaries (`train_end_step: 500`, `val_end_step: 580`), calibration policy, leakage-gate defaults (`min_behavioural_pr_auc: 0.50`, `max_ablation_pr_auc_delta: 0.20`, `importance_repeats: 5`) |
| `governance.yaml` | Rationale depth **above** the floor (`richer_rationale_required_for_actions: [escalate]`, `richer_rationale_required_on_deviation: true`) |
| `queue_policy.yaml` | Queue ordering (`default_sort: risk`, `allowed_sorts: [risk, case_age]`) |

---

## 7. Repository structure

```
├── PROJECT_CONTEXT.md        this document — orientation
├── CHANGELOG.md              release history
├── README.md                 project overview and quick start
├── config/                   versioned governance configuration (I-4)
├── src/tfm/
│   ├── schema/               canonical evidence schema — every module imports this
│   ├── data/                 ingestion; point-in-time features; out-of-time splits
│   ├── ml/                   Scorer interface, candidates, training, calibration, registry
│   ├── rules/                deterministic rule engine and definitions
│   ├── recommendation/       advisory policy (absent-score + present-score paths)
│   ├── assembly/             evidence assembler; the groundable set
│   ├── explanation/          Explainer interface, templated explainer, LLM stub, grounding gate
│   ├── queue/                queue ordering policy
│   ├── audit/                append-only log, decision snapshot, reconstruction
│   ├── persistence/          SQLAlchemy 2.0 typed models and sessions
│   ├── services/             orchestration (case, queue, disposition)
│   ├── api/                  FastAPI online path
│   ├── web/                  Streamlit analyst workspace
│   ├── config/               settings loading and validation
│   └── observability/        structured logging
├── evaluation/               standalone offline evaluation package
│   └── reports/              committed evaluation artifacts (see §9)
├── migrations/               Alembic schema migrations
├── notebooks/                01_data_understanding, 02_scoring_and_leakage_gate
├── scripts/                  train_model, seed_cases, package_evaluation
├── tests/                    unit + integration (249 passing at v1.0.0)
└── docs/
    ├── PROJECT_DOCUMENTATION.md   the full engineering reference (why)
    ├── V1_RETROSPECTIVE.md        the engineering story
    ├── archive/v1-hackathon/      hackathon-artifact pointers
    └── internal/                  original design records (provenance)
```

---

## 8. Deployment architecture

Two processes plus a database. A FastAPI service serves the decision API; a Streamlit
application provides the analyst workspace and calls that API; a database holds the
operational tables and the append-only audit log. The same code runs in all three
environments below.

**Local development (SQLite, no Docker).** Two processes against a local SQLite file:
`alembic upgrade head` → `python scripts/seed_cases.py` (idempotent) → Uvicorn on `:8000`;
then Streamlit on `:8501` pointed at `API_BASE_URL`. The LLM is disabled by default, so
the stack runs on the templated grounded-explanation floor with no external provider.

**Local development (Docker Compose, PostgreSQL).** `docker compose up` brings up `db`
(postgres:16), `api` (applies migrations, runs the idempotent seed, then serves), and
`web`. A clean volume produces a populated queue with no manual step.

**Live deployment.** The FastAPI service is deployed on **Render** (interactive docs at
`/docs`); the analyst workspace is deployed on **Streamlit Community Cloud**, configured to
call the Render-hosted API.

**A correct launch on any path:** the queue opens with 5 cases, the 2 escalate cases on
top, then three holds. An empty queue means the seed did not run against that database.

Detail: `README.md` (commands) and `docs/PROJECT_DOCUMENTATION.md` §15.

---

## 9. Audit architecture

- **Append-only** (`audit/log.py`, table `audit_log`). The `AuditWriter` exposes `append`
  and nothing else. Enforced at the application writer, by a PostgreSQL trigger created in
  the initial migration, and — in production — by revoking `UPDATE`/`DELETE` at the
  database role level.
- **Per-case events:** `case_assembled`, `explanation_generated`, `disposition_recorded`.
- **The decision snapshot.** At disposition the system writes a single
  `disposition_recorded` event carrying a complete, self-contained, versioned, immutable
  snapshot: what was shown (the rendered `EvidencePackage`), what was decided (action,
  reason code, rationale, deviation flag), what was recommended, what was explained, how it
  was routed, and provenance.
- **Rendered artifacts are snapshotted, not inputs plus configuration.** This is
  deliberate. Templated copy, rule parameters, and thresholds change over time; re-deriving
  a past decision from inputs and *today's* configuration would reproduce today's output,
  not what the analyst actually saw.
- **Reconstruction is pure deserialization** (`audit/reconstruct.py`). It reads one row and
  validates its snapshot back into typed objects — no rule engine, no policy, no
  explanation generation, no grounding gate, no configuration, no operational table. The
  audit log is the sole source. This is invariant **I-3**.

---

## 10. Evaluation architecture

**Offline and online are separate paths.** The audit log is the only bridge: written by the
online path, read by the offline path. Version 1 captures learning signals but does not
consume them — the feedback loop is deferred by design (FR-21).

**One command reproduces every artifact:** `python -m evaluation.run_all`.

**The runner reads the committed model-training artifacts verbatim.** It does not retrain,
recalibrate, or regenerate any model metric. Model metrics, eligibility, and the model
version come from the committed scorer manifest; the full leakage verdict comes from
`leakage_verdict.json`. Only the grounding report — genuinely measurable on synthetic
cases — is computed fresh.

**`evaluation_manifest.json` is the single source of truth.** It lists the consolidated
artifacts, so downstream packaging (`scripts/package_evaluation.py`) references no
hardcoded filenames.

**Committed artifacts under `evaluation/reports/`:**

| Artifact | Contents |
|---|---|
| `evaluation_manifest.json` | Model version, dataset, leakage verdict, eligibility, artifact list |
| `evaluation_summary.json` | Headline (leads with **SCORER INELIGIBLE**), metrics, calibration, grounding, disclosures |
| `leakage_verdict.json` | Standalone verdict and full evidence for the selected model |
| `tfm-scorer-20260703224313_training_report.json` | Baseline run — the leakage discovery |
| `tfm-scorer-20260704053632_training_report.json` | Remediated run — the selected, excluded model |

**Reported figures for the selected model** (`tfm-scorer-20260704053632`), every one a
**modelled estimate on synthetic PaySim**, attached to a model whose verdict is FAIL:
PR-AUC 0.3209, precision 0.9756, recall 0.1792, ROC-AUC 0.9174, calibrated Brier 0.0086
(isotonic).

**Grounding — the one thing that is *measured* on the shipped product**
(`grounding_report.json`, 6 synthetic held-out cases, LLM disabled): ungrounded-statement
rate **0.0**, total ungrounded tokens **0**, templated fallback rate **1.0**.

What is measured on the shipped product is the **governance behaviour**, not a predictive
metric.

---

## 11. Known limitations of Version 1

Stated openly because they bound what any metric here can mean.

- **The dataset could not support the product's core premise.** Approximately **99.85%** of
  PaySim origin accounts appear only once, so the per-account behavioural history the
  product is built around barely exists in the data. This caps the behavioural ceiling of
  any model on this data at roughly PR-AUC 0.34.
- **The scorer is excluded.** The operational path runs on deterministic rules alone. This
  is honest and it works, but it is a *degraded* mode, not the intended one.
- **Simulator leakage.** PaySim cancels a fraudulent transaction after flagging it,
  reversing the money — so the balances themselves encode the label. This is a property of
  the data-generating process, not a modelling error.
- **Clean synthetic labels** make evaluation optimistic relative to real fraud labelling.
- **Short span.** ~31 days of simulation prevents any seasonality or drift assessment.
- **No protected attributes.** Demographic fairness cannot be assessed on PaySim, and no
  proxy is manufactured to pretend otherwise.
- **No production hardening.** Authentication, authorisation, retention, and database-level
  append-only enforcement on the audit store are documented deployment obligations
  (BL-M8-01), deferred.

---

## 12. Where to read more

| To understand | Read |
|---|---|
| Why each decision was made — the full engineering reference | [`docs/PROJECT_DOCUMENTATION.md`](docs/PROJECT_DOCUMENTATION.md) |
| The leakage discovery, the remediation, and what it proved | [`docs/V1_RETROSPECTIVE.md`](docs/V1_RETROSPECTIVE.md) |
| What shipped in v1.0.0 | [`CHANGELOG.md`](CHANGELOG.md) |
| Every requirement → implementation → covering test | `docs/internal/TRACEABILITY.md` |
| Milestone-by-milestone build record | `docs/internal/PROGRESS.md` |
| Decisions taken during implementation (IMP-001…IMP-011) | `docs/internal/IMPLEMENTATION_DECISIONS.md` |
| The approved product specification (DDR-01 is Appendix A) | `docs/internal/01_Product_Specification.md` |
| Where the hackathon artifacts live | `docs/archive/v1-hackathon/README.md` |
| How to run it | `README.md` |

---

*All quantitative results in this document were measured on synthetic PaySim data. The
machine-learning scorer is ineligible under the simulator-leakage gate and is excluded from
the operational path. No claim of real-world fraud-detection performance is made.*
