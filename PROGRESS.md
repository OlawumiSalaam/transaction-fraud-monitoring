# Implementation Progress

## M0 — Project Bootstrap

Status: ✅ Validated

### Completed

- Repository skeleton with `uv`-managed dependencies and locked `pyproject.toml`
- Typed configuration loading via pydantic-settings and versioned YAML config files
- Structured logging scaffold (`structlog`)
- PostgreSQL + Alembic migrations (`0001_initial_schema.py`) — full canonical schema DDL including the append-only trigger on `audit_log`
- SQLAlchemy 2.0 typed ORM models and session management
- `AuditWriter` scaffold (insert-only; payload assembly deferred to M4–M8)
- FastAPI skeleton with `/health` endpoint and DI wiring
- Streamlit workspace stub
- Docker Compose and `.env.example`
- CI skeleton (lint / type-check / test)
- All layer package stubs with interfaces in place (no business logic)

### Simplified

None

### Stubbed

- All layer packages (`ml/`, `rules/`, `recommendation/`, `assembly/`, `explanation/`, `queue/`, `data/`, `schema/`) — interfaces and `__init__.py` files only; no implemented product logic.

### Deferred

None (M0 scope is bootstrap concerns only per Implementation Plan §6)

### Verification

Validation executed 2026-07-03:

```
ruff check .       → All checks passed!
mypy               → Success: no issues found in 44 source files
pytest             → 11 passed in 2.09s
```

IC-001 resolved: Ruff violations in `migrations/versions/0001_initial_schema.py` corrected (import ordering + line-length wrapping). No schema semantics altered.

### Implementation Concerns

IC-001 — Bootstrap migration fails Ruff formatting validation — **Resolved 2026-07-03**

### Backlog

None

---

## M1 — Canonical Evidence Schema and Data Ingestion

Status: ✅ Approved (closed 2026-07-03)

### Completed

- **Canonical Evidence Schema** (`src/tfm/schema/entities.py`): `TransactionType` (StrEnum),
  `Transaction`, `Account`, `Counterparty`, `AccountBehaviouralProfile`,
  `BeneficiaryRelationship` — all Pydantic frozen models per §6.2.
- **FeatureVector** (`src/tfm/schema/evidence.py`): shared feature substrate for the rule
  engine (M3) and evidence assembler (M4); the ML scorer trains on the
  `PRIMARY_FEATURE_COLUMNS` subset after the IMP-011 balance-artifact quarantine — per
  §6.5, FR-5.
- **PaySim ingestion** (`src/tfm/data/ingest.py`): `load_paysim_csv()` mapping PaySim columns
  to canonical names, `event_ts` derivation, merchant detection (M-prefix), balance nulling
  for merchant destinations, stable `txn_id` from row position; `ingest_to_db()` upserts
  accounts/counterparties, inserts transactions idempotently.
- **Point-in-time feature builder** (`src/tfm/data/features.py`): `build_features()` with
  four feature families: transaction-intrinsic (type encoding), balance/sequence
  (`frac_bal_orig_moved`, `orig_account_emptied`), account-behavioural 24 h sliding
  window (`txn_count_24h`, `amount_sum_24h`), counterparty (`is_new_counterparty`,
  `distinct_counterparties_seen`). O(n) sliding window with per-account groupby.
  `FEATURE_COLUMNS` constant; `to_feature_vector()` for online scoring path.
- **Out-of-time split** (`src/tfm/data/splits.py`): `DataSplit` frozen dataclass;
  `make_out_of_time_split()` with default boundaries train_end=500, val_end=580 for
  PaySim 744-step simulation. Random splits prohibited.
- **Post-approval hardening** (`pyproject.toml`): Streamlit floor >=1.58 (IMP-002);
  pandas/numpy promoted to base deps (IMP-003).
- **Tests**: 76 new tests across `test_schema.py`, `test_ingest.py`, `test_features.py`,
  `test_splits.py`. Includes two Hypothesis property tests: `test_features_point_in_time_invariant`
  (sliding-window mechanism, `txn_count_24h`) and `test_features_counterparty_prior_transactions_invariant`
  (set-accumulation mechanism, `is_new_counterparty` + `distinct_counterparties_seen`).
  Shared-mechanism rationale documented in IMP-005.
- **Notebook**: `notebooks/01_data_understanding.ipynb` — dataset validation, canonical schema
  confirmation, class balance, sim_flagged exclusion rationale, merchant balance invariant,
  OOT split preview, ingestion smoke test.

### Simplified

- `ingest_to_db` uses legacy `session.query()` API for existence checks. SQLAlchemy 2.0
  `select()` would be idiomatic but the result is functionally equivalent for V1.

### Stubbed

None — all M1 scope is fully implemented.

### Deferred

- Batch / streaming ingest path (deferred to post-hackathon)
- `bal_dest_before` / `bal_dest_after` imputation strategy — deferred to M2 (scorer decides)
- `AccountBehaviouralProfile` and `BeneficiaryRelationship` Pydantic entities are defined in
  the schema but are populated from DataFrame features, not from a persistent profile store;
  persistent profile storage is a post-hackathon concern.

### Verification

Validation executed 2026-07-03:

```
ruff check .       → All checks passed!
mypy               → Success: no issues found in 44 source files
pytest             → 87 passed in 36.32s
```

New tests: 76 (schema: 11, ingest: 25, features: 24, splits: 16)
Hypothesis property tests (200 examples each, deadline=None):
  - `test_features_point_in_time_invariant` — sliding-window boundary (txn_count_24h)
  - `test_features_counterparty_prior_transactions_invariant` — set-accumulation boundary
    (is_new_counterparty + distinct_counterparties_seen)
sim_flagged exclusion verified: not in FEATURE_COLUMNS, not in FeatureVector.
IMP-004 (bal_dest imputation deferral) and IMP-005 (property-test scope rationale) recorded.

### Implementation Concerns

None.

### Backlog

- BL-M1-01: Replace `session.query()` legacy style with SQLAlchemy 2.0 `select()` style
  when the project-wide ORM layer is modernised (post-hackathon).
- BL-M1-02: Explore vectorised feature computation (replace Python groupby loop with
  pandas GroupBy rolling operations) if performance is required at scale.
- BL-M1-03: Hypothesis deadline suppressed (`deadline=None`) for property tests due to
  Windows pandas overhead on the CI machine. Review if CI migrates to Linux.

---

## M2 — Fraud Scoring and the Simulator-Leakage Gate

Status: ✅ Implemented (awaiting reviewer approval)

### Completed

- **Scorer contract** (`src/tfm/ml/model.py`): `Score` / `ContributingSignal` frozen types
  (Addendum §4), the `Scorer` protocol, and `FittedScorer` producing a calibrated probability
  plus contributing signals from pinned permutation-importance + association-direction metadata.
- **Bounded candidate set** (`src/tfm/ml/candidates.py`): HistGradientBoosting interpretable
  primary, LightGBM kitchen-sink comparator (augmented features), logistic-regression floor.
  Each owns its preprocessing (IMP-006).
- **Candidate-private preprocessing** (`src/tfm/ml/preprocess.py`): canonical-immutable matrix
  extraction; imputation/scaling fitted on train only. The M1 feature dataset is never mutated.
- **Shared fit primitives** (`src/tfm/ml/pipeline.py`): `fit_candidate`, `predict_proba`,
  permutation-importance (PR-AUC), training-set association directions.
- **Calibration** (`src/tfm/ml/calibration.py`): isotonic / Platt with the small-fold guard
  (R14), fitted on validation only; `CalibratedModel` wrapper. Method auto-chosen by val Brier.
- **Training orchestration** (`src/tfm/ml/train.py`): OOT split → fit+calibrate each candidate →
  OOT-test metrics → leakage gate for the two DF-1 candidates → DF-1 comparison → selection
  (interpretable primary iff it passes the gate; a failing primary is ineligible and not
  silently replaced) → `FittedScorer` + JSON `TrainingReport`.
- **Model registry** (`src/tfm/ml/registry.py`): artifact save/load; only a gate-passing
  version is loadable in the online path (`IneligibleModelError`) — FR-4 enforced.
- **Evaluation package** (`evaluation/`): `model_eval.py` (PR-AUC, precision, recall, ROC-AUC,
  Brier — FR-22); `leakage_gate.py` (feature-importance + ablation + evidence-based verdict —
  FR-26, IMP-007); `calibration_report.py` (reliability bins + Brier — FR-23).
- **Model config** (`config/model.yaml` + `ModelConfig`): split boundaries, seed, eval
  threshold, quarantined balance-artifact features, augmented features, calibration policy,
  and leakage-gate decision-support defaults (versioned; IMP-007).
- **Training CLI** (`scripts/train_model.py`): offline entry producing the scorer artifact +
  report + leakage-verdict JSON from real PaySim.
- **Notebook** (`notebooks/02_scoring_and_leakage_gate.ipynb`): descriptive; ends with a
  Leakage Verdict Summary (primary model, ablation model, verdict, supporting evidence).
- **Implementation decisions**: IMP-006 (canonical immutability), IMP-007 (evidence-based
  verdict), IMP-008 (CI `[ml]` extra + root `evaluation/` package tooling).
- **Tests**: 49 new tests across `test_model_eval`, `test_preprocess`, `test_candidates`,
  `test_calibration`, `test_model`, `test_leakage_gate`, `test_train`. The gate is verified in
  both directions — it PASSES a behavioural synthetic dataset and FAILS a leaky one.

### Simplified

- Model hyperparameters are fixed engineering defaults (not swept). Full hyperparameter tuning
  is deferred (Release Plan B-items); governance-sensitive parameters are in config.
- Contributing signals use pinned global permutation importances + training-set association
  direction (deterministic, interpretable), not per-instance attribution (e.g. SHAP).

### Stubbed

None — all M2 scope is implemented behind real interfaces.

### Deferred

- Producing the **committed** PaySim-trained model artifact (Release Plan §5) is a documented
  developer step: run `scripts/train_model.py --data <paysim.csv>`. The pipeline, gate, and
  tests are complete; committing the binary artifact requires the PaySim CSV locally and is
  wired into the demo in M10. No fake/synthetic-trained artifact is committed (honesty).
- Threshold sensitivity and the full cost model are M5 (governance-first operating point).

### Verification

Validation executed 2026-07-03:

```
ruff check .                          → All checks passed!
ruff format --check src tests evaluation → 68 files already formatted
mypy                                  → Success: no issues found in 51 source files
pytest                                → 136 passed in ~78s
```

New tests: 49 (model_eval: 5, preprocess: 7, candidates: 7, calibration: 7, model: 8,
leakage_gate: 5, train+registry: 10). Total suite now 136 (87 from M0/M1 + 49 M2, plus
prior additions).

Leakage gate verified in both directions:
- behavioural synthetic dataset → verdict PASS (behavioural signal survives ablation)
- leaky synthetic dataset → verdict FAIL (performance collapses; artifact importance share > 50%)

Canonical immutability verified: `run_training` does not mutate the input features DataFrame.
FR-4 enforced: registry refuses to load a non-gate-passing model in the online path.

### Full-scale execution and remediation cycle 1 (2026-07-04)

The first full-scale run on the complete PaySim dataset (6,362,620 rows) required a
memory fix to the M1 feature builder (single-pass traversal; IMP-009) and then
executed the leakage gate on real data:

- **Baseline `tfm-scorer-20260703224313` → FAIL.** The interpretable primary rode
  balance-consistency artifacts (98.5% permutation-importance share; behavioural
  PR-AUC 0.3365 on ablation). Correct FR-4/§9 behaviour; recorded, `eligible=false`.
- **Remediation cycle 1 `tfm-scorer-20260704053632` → FAIL (IMP-011).** Balance
  artifacts quarantined from the primary (importance share 0.0%, ablation delta
  0.0000); two §9 behavioural features + one bounded extension added. Behavioural
  sufficiency still failed: `remaining_behavioural_pr_auc` 0.3369 < 0.50. The new
  features contributed ~0 (top signals: `amount`, transaction `type_*`), confirming
  PaySim's draining typology is intrinsically balance-identity-driven (§6.6).
  Thresholds were **not** tuned (M2 fixed decision — leakage is never hidden).

Per-version reports for both runs are retained under `evaluation/reports/`. The
next step is a governance decision: a second bounded cycle with a different
behavioural hypothesis (e.g. counterparty concentration), or shipping the
documented failure per Release Plan B15.

### Implementation Concerns

None. (The persistent leakage FAIL is the governance layer functioning as designed,
not a blocking ambiguity; the eligibility decision and next-step options are recorded
in IMP-011 and pending a governance decision.)

### Backlog

- BL-M2-01: Full bounded hyperparameter comparison / tuning (Release Plan B3).
- BL-M2-02: Per-instance signal attribution (e.g. SHAP) behind the same `ContributingSignal`
  interface, if richer explanations are required (currently global importances + direction).
- BL-M2-03: Commit the PaySim-trained scorer artifact and wire it into `docker compose` (M10).
- BL-M2-04: Subgroup / false-positive-burden analysis (FR-25) — consolidated in M9.

---

## M3 — Deterministic Rule Engine

Status: complete (pending commit). The gate-ineligible scorer (M2) is excluded from the
operational path under FR-4; the deterministic rule engine is the case's primary
operational **evidence source** — graceful degradation, not a workaround. M3 is judged as
an engineering milestone — architectural completeness, deterministic behaviour,
explainability, and evidence generation — independent of how thoroughly the supplied
PaySim dataset exercises each rule.

Three concepts are kept distinct: a rule is **implemented** (present in the registry),
**enabled** (available for evaluation — the engine runs it and emits a RuleHit when it
fires), and **exercised by the supplied dataset** (actually fires on PaySim). Enabled
does not mean "drives a recommendation": RuleHits are evidence; the M5 policy maps them to
clear/hold/escalate and the human analyst makes the final disposition (M7).

### Completed

- **`RuleEngine`** (`src/tfm/rules/engine.py`): evaluates the config-enabled rules over a
  single `FeatureVector` and returns `[RuleHit]`. Pure, deterministic, **independent of the
  ML score** (Addendum §4; Layer Separation); constructed from the versioned `RulesConfig`.
- **Domain `RuleHit`** (`src/tfm/schema/evidence.py`): auditable evidence — `rule_id`,
  human-readable `summary`, and the `evidence` dict of the fields + thresholds that fired.
- **Rule definitions** (`src/tfm/rules/definitions.py`), all auditable if-then, parameters
  from `config/rules.yaml`, over canonical M1 features only:
  - `account_draining` — `frac_bal_orig_moved >= min_fraction_of_balance` (§6.5; FR-6).
  - `velocity` — `txn_count_24h >= max_transactions` (M1 24 h window).
  - `new_beneficiary_large` — `is_new_counterparty ∧ amount >= amount_threshold`.
  - `mule_passthrough` — registered extension-point stub (no-op); real logic deferred to M4
    (IC-M3-01).
- **Enabled set** (`config/rules.yaml`): account_draining, velocity, new_beneficiary_large.
  `mule_passthrough` is implemented in the registry but not enabled (deferred to M4).
- **Dormant-account reactivation** excluded, documented, no proxy (config; not in
  `KNOWN_RULE_IDS`) — FR-7.
- **Balance features in deterministic rules are legitimate**: the IMP-011 quarantine applied
  only to the ML scorer's *learned* dependence; §6.5 names the balance/sequence family for
  rules and FR-6 names account-draining. A transparent rule is not simulator leakage.

### Traceability

FR-6, FR-7; §6.5, §6.6; Addendum §4 (Rule Engine contract); Release Plan M3; Implementation
Plan M3; Principle: Layer Separation, Layer Visibility, Governance (parameters in versioned
config).

### Verification

`tests/unit/test_rules.py` — 17 tests: each real rule fires/does-not-fire on constructed
fixtures; parameters sourced from config; engine returns hits in enabled order and respects
an enabled subset; determinism; independence-from-score (structural); `REGISTRY` covers
`KNOWN_RULE_IDS`; RuleHit evidence is auditable; the shipped `config/rules.yaml` evaluates.
Full suite green; Ruff + mypy clean.

### Assumptions

- `velocity` is bound to the M1 feature's fixed 24 h window; `window_hours` in config is
  recorded as evidence and expected to be 24.

### Deviations

- Release Plan M3 named `account_draining` + `mule_passthrough` as the two real rules.
  `mule_passthrough` requires cross-account peer/chain analysis the governing documents place
  under Future work (IC-M3-01) and ships as the documented extension-point stub; `velocity`
  and `new_beneficiary_large` — clean single-transaction if-then rules — are enabled instead,
  so the engine ships three real, evaluable rules. The Release Plan permits the enabled set to
  reflect what ships.
- Whether the supplied PaySim dataset exercises every enabled rule is a **documented dataset
  limitation** (narrow typology; no per-account longitudinal history — §6.6), not an
  implementation failure, and is out of scope for further analysis.

### Implementation Concerns

- **IC-M3-01 — `mule_passthrough`: activation route is Future work (§517), not M4.** Revisiting
  the governing documents by precedence: the Evidence Assembler's defined inputs (Addendum §4)
  are *transaction + account history + counterparty + score + rule hits* — the origin account's
  history and the counterparty **record**, not the counterparty's transaction chain. The seven
  evidence requirements answer "broader pattern" with *counterparty linkage + direction +
  balances* (§265), and M4's Definition of Done is satisfied without an inbound leg. Full
  cross-account **network / link analysis for mule structures is explicitly Future work** (Spec
  §517). So M4 is **not** the architectural point where peer-chain evidence belongs, and M4 does
  not require it. `mule_passthrough` remains the registered extension-point stub; its
  specification-supported activation route is the Future network/link-analysis track (§517) — a
  richer dataset/deployment activates it there. Not an invariant violation; not an M4 obligation.

### Backlog

- BL-M3-01: `mule_passthrough` real logic via the Future network/link-analysis track for mule
  structures (Spec §517; Release Plan B5; IC-M3-01).
- BL-M3-02: `account_draining` refinements (e.g. an `applies_to_types` config parameter) —
  optional; deferred to a deployment with a broader fraud typology.

---

## M4 — Evidence Assembly

Status: complete (pending commit). The assembler builds, per flagged transaction, the
`EvidencePackage` that answers the seven evidence requirements (§265, FR-2) and defines the
groundable evidence set consumed by M5 (recommendation), M6 (explanation/grounding), and M7
(case view). Pure function of domain inputs — it assembles; it does not score, recommend,
explain, rank, or decide (Layer Separation).

### Completed

- **Domain types** (`src/tfm/schema/evidence.py`): `EvidenceElement` (element_id, label,
  `source`, `raw`, `groundable`, `requirements`), `ScoreStatus` (assembler input describing
  score availability), `EvidencePackage` (element-centric; derives the groundable set and the
  seven-requirement coverage from the elements — no parallel indexes).
- **`assemble_evidence`** (`src/tfm/assembly/assembler.py`): maps each of the seven
  requirements to canonical/rule/score-sourced elements; every element traces to a source
  (total traceability invariant).
- **Element-centric groundable contract (Q2)**: `GroundableEvidence` = the subset of elements
  with `groundable = True`. Single completeness invariant — *every value or entity M6 may
  reference must trace to a groundable EvidenceElement* — with no numeric/entity collections to
  keep in sync.
- **Honest degradation states**:
  - *FR-4 score exclusion*: a populated `score_signal` element carrying the exclusion reason,
    `leakage_verdict`, and `excluded_under = "FR-4"` — but **no probability**, so a score claim
    is structurally ungroundable. The scorer is not reintroduced into operational decisions.
  - *First-observed account*: an explicit no-baseline `account_history` element whose stated
    reason ("first observed transaction; no behavioural baseline available") is itself groundable.
- **Groundable classification (documented)**: evidentiary elements (transaction facts,
  direction+balances, interpretable features, account history/no-baseline, counterparty, rule
  hits, score signal) are groundable; the synthetic-data **disclosure** is display-only
  (`groundable = False`) — shown to the analyst (FR-13) but not an evidentiary risk claim.

### Traceability

FR-2 (assemble seven requirements, push), FR-13 (disclosure); §265, §6.2, §6.4, §6.7; Addendum
§4 (Evidence Assembler contract); Release Plan M4; Implementation Plan M4; Principle: Layer
Separation, Canonical Evidence Schema.

### Verification

`tests/unit/test_assembler.py` — 12 tests: all seven requirements covered; **total** traceability
over every element; expected elements groundable and the disclosure display-only; FR-4 exclusion
is an explicit structured element with no probability anywhere in the groundable set; first-observed
emits the groundable no-baseline element with the stated reason; account-with-history emits the
behavioural summary; determinism. Full suite: **177 passed**; Ruff + `ruff format --check` + mypy clean.

### Assumptions

- First-observed detection uses `prior_transaction_count` supplied by the caller (0 → no baseline).
- Account-history evidence is scaled to the shipped feature set (Release Plan M4 "Simplified");
  richer derived aggregates are deferred (backlog B6).

### Deviations

- Score is represented **element-centrically** (a `score_signal` element) rather than as the
  separate `ScoreEvidence`/`ScoreExclusion` wrapper from the earlier proposal — collapsing to
  one representation per the approved Q2 contract; the FR-4 exclusion falls out naturally.
- Disclosures are modelled as a display-only `EvidenceElement` (source `disclosure`) so all
  seven requirements map uniformly to elements; the `EvidenceSource` enum extends the Addendum's
  five illustrative sources by this one display-only source.
- `mule_passthrough` remains deferred (IC-M3-01): M4's inputs and DoD do not include peer-chain
  evidence; its activation route is Future work (§517), not an M4 obligation.

### Implementation Concerns

- None new. IC-M3-01 stands, now with the corrected §517 Future activation route (see M3 above).

### Backlog

- BL-M4-01: Richer derived evidence aggregates (Release Plan B6; FR-2).
- BL-M4-02: Persist the assembled `EvidencePackage` into `audit_log.evidence` at disposition
  (M8) and serve it via `GET /api/cases/{id}` (M7); the assembler output is the source object.

---

## M4 — Implementation Summary

- **Element-centric GroundableEvidence contract**: the assembler emits `EvidenceElement`s; the
  groundable set is exactly the `groundable = True` subset (`EvidencePackage.groundable_elements`).
  One completeness invariant — every referenceable value/entity traces to a groundable element —
  replaces any numeric/entity synchronisation. This is the formal M4→M6 boundary: M6 may reference
  only groundable elements, and the grounding gate validates every generated number/entity against
  that set.
- **Honest degradation states**: (a) the ineligible scorer is an explicit `score_signal` element
  stating exclusion under FR-4 with no probability — a score claim cannot be grounded; (b) a
  first-observed account yields an explicit, groundable no-baseline element with its stated reason.
  Both are structured, not blank/omitted/inferred.
- **Corrected IC-M3-01**: `mule_passthrough`'s activation route is the Future network/link-analysis
  track (Spec §517), not an M4 assembler extension; M4's inputs and Definition of Done do not
  require peer-chain evidence.
- **Seven evidence requirements**: all seven remain satisfied — verified by
  `requirement_coverage()` returning a non-empty element set for each of 1..7, asserted in tests.

---

## M5 — Recommendation Policy

Status: complete (pending commit). A pure, deterministic, **advisory** policy mapping
*(score band, rule hits)* → `clear | hold | escalate`. It never decides (the analyst is the
sole decider); it does not score, explain, rank, or route.

### Completed

- **`recommend`** (`src/tfm/recommendation/policy.py`): pure deterministic function, total over
  every (score band × rule-hit) combination. Emits `Recommendation { action, confidence,
  basis {score_band, rule_ids}, uncertainty_flag }` (Addendum §4).
- **Two paths, one architecture**:
  - *Absent-score (operational, ships under FR-4)*: recommends solely from rule evidence and
    **never returns `clear`** — a clear would assert trustworthy low-risk assurance the excluded
    scorer cannot provide. Escalating rule → escalate; other fired rule → hold; no hits → hold
    with `uncertainty_flag`. `score_band = "none"`; `uncertainty_flag` always set (no score).
  - *Present-score (future-ready)*: (band × rule signal) truth table, most-severe-wins;
    borderline floors at hold. An eligible scorer later flips `ScoreStatus.available` and
    activates this path with no policy change.
- **Config-sourced** (`config/thresholds.yaml`): `score_bands` + `recommendation.escalating_rules`
  (validated against `KNOWN_RULE_IDS`); no literals in logic.

### Traceability

FR-8 (advisory recommendation), FR-9 (governance-first thresholds), §11.2 (deterministic policy;
borderline → hold; uncertainty propagates); Addendum §4; Release Plan M5; Implementation Plan M5;
Principle: Human in the Loop, Governance, Graceful Degradation.

### Verification

`tests/unit/test_recommendation.py` — 27 cases: absent-score escalate/hold/thin-evidence;
**never-clear** across all rule combinations; present-score low→clear, high→escalate,
borderline→hold, low+escalating-rule→escalate (conflict-flagged); **totality** over
(band × rule-signal); config-driven escalation; shipped-config loads escalating rules;
determinism. Full suite: **204 passed**; Ruff + `ruff format --check` + mypy clean.

### Assumptions

- Confidence is a coarse deterministic indicator: `high` on a decisive score signal (band
  low/high, no conflict), `low` on thin evidence (no score, no rules), else `medium`.

### Deviations

- Full **threshold-sensitivity analysis is deferred to M9** (Impl Plan line 221); the config
  defaults carry a documented *modelled* rationale. Score bands are operationally dormant while
  the scorer is excluded, so the present-score path is future-ready but unexercised.

### Implementation Concerns

- None.

### Backlog

- BL-M5-01: Cost-model / threshold-sensitivity analysis for the score bands, consolidated in M9
  (§11.2, FR-9), when/if an eligible scorer exists.

---

## M5 — Implementation Summary

- **Advisory, deterministic, total**: `recommend` maps (score band, rule hits) → clear/hold/escalate
  as a pure function, property-tested total over every combination; it carries its basis and an
  uncertainty flag and never makes the decision (Human-in-the-Loop).
- **Honest absent-score operational path (confirmed behaviour)**: with the scorer excluded under
  FR-4, the policy recommends **only** hold or escalate from rule evidence and **never clears** —
  a clear would assert an assessment the system cannot make without a trustworthy score.
- **Future-ready present-score path**: the (band × rule) truth table (borderline → hold) activates
  unchanged when an eligible scorer is introduced — one architecture, two paths.
- **Governance-sourced thresholds**: score bands and the escalating-rule set live in
  `config/thresholds.yaml`, validated; no literals in the policy.
- **Verification**: 27 policy tests including a full totality sweep; full suite 204 passed; clean.

---

## M6 — Explanation & Grounding

Status: complete (pending commit). Ships on the **templated floor** (Release Plan/CLAUDE.md
M6 fixed decision): the templated explainer, deterministic grounding gate, and graceful
fallback are real; the LLM is a documented stub behind the real `Explainer` interface. The
explainer *consumes* evidence and explains the assembled evidence + recommendation — not
model internals (the scorer is operationally excluded, FR-4).

### Completed

- **`Explainer` interface + `explain()` orchestrator** (`explanation/explainer.py`): fallback
  order LLM → gate → pass ? LLM : templated; LLM disabled/unavailable/grounding-failed →
  templated. No error path for LLM issues (NFR-2). `Explanation {text, pathway, ai_generated,
  grounding}`.
- **`TemplatedExplainer`** (`explanation/templated.py`): deterministic, **grounded by
  construction** — each sentence is generated from a named groundable element (or the
  recommendation, which traces to elements) and records its `source_element_ids`; numbers are
  rendered losslessly and entities copied verbatim, so its own output provably passes the gate.
- **`GroundingGate`** (`explanation/grounding.py`): deterministic (never a model). Builds the
  reference set from the groundable elements + the recommendation's controlled vocabulary
  (numbers, entities, rule ids, action/confidence/score-band, thresholds, FR-4). Verifies every
  numeric and entity token after canonical normalization ($, commas, %); on failure signals
  fallback. Templated path bypasses (grounded by construction).
- **`LLMExplainer`** (`explanation/llm_explainer.py`): documented stub — raises `LLMUnavailable`
  so the fallback engages; never fabricates output (backlog B8).

### Grounding contract (refined — element-centric, claim-level)

The contract goal is **every factual claim traces to ≥1 groundable EvidenceElement**, enforced
two ways: (a) **by construction** on the shipped templated path — sentence→element provenance,
so every claim is reconstructable from named elements; (b) by the **broadened deterministic
token gate** for the (future) LLM path — numbers, entities, rule ids, recommendation actions,
score-exclusion / no-baseline terms, and thresholds must all appear in the element-derived
reference set. The gate remains mechanical (deterministic code, never a model); full semantic
claim-entailment is out of scope for a deterministic gate by design.

### Traceability

FR-10, FR-11, FR-12, FR-13, FR-24; §3, §5.5, §8, §11.2, §357; Addendum §4; Risk R4/R5;
Principle: Grounding, Graceful Degradation, Layer Separation.

### Verification

`tests/unit/test_explanation.py` — 13 tests: templated output **passes the gate** (grounded by
construction); gate **rejects** a planted ungrounded number and entity; canonical $/comma/%
normalization (R4); LLM disabled and LLM-stub-enabled both fall back to templated (NFR-2); the
**five degradation states** (scorer excluded, no baseline, no rules, one rule, multiple rules)
produce honest text with no invented information; determinism + AI-generated label; `Explainer`
protocol satisfied. Full suite: **217 passed**; Ruff + `ruff format --check` + mypy clean.

### Assumptions / Deviations

- The **ungrounded-rate ≈ 0** guarantee holds **by construction** on the templated floor; its
  *measurement* (ungrounded / fallback rates on held-out cases, FR-24) is consolidated in **M9**.
- Generation **timing** (eager vs on-open, §5.5) is deferred to M7/M10 wiring — not fixed here.

### Implementation Concerns

- None.

### Backlog

- BL-M6-01: minimal single-provider `LLMExplainer` behind the interface + constrained prompt
  (Release Plan B8; FR-10).
- BL-M6-02: measure ungrounded-statement and fallback rates on held-out synthetic cases (M9; FR-24).

---

## M6 — Implementation Summary

- **Grounding contract (as you refined it)**: every factual claim must trace to a groundable
  `EvidenceElement`. Enforced by construction on the templated floor (each sentence records its
  source element ids) and by a broadened deterministic token gate for the LLM path — while
  keeping the gate mechanical (never a model).
- **Explanation strategy**: template-driven, LLM-stubbed — the governing M6 fixed decision. The
  templated explainer is real and grounded by construction; the LLM sits behind the interface,
  disabled, activatable later by config with no architecture change.
- **Graceful degradation** proven for all five states — scorer excluded (FR-4), no baseline, no
  rules, one rule, multiple rules — each an honest explanation with no invented information and
  uncertainty surfaced, matching the recommendation.
- **Auditability**: the templated explanation is a pure deterministic function of
  `(EvidencePackage, Recommendation)` — re-running the explainer reproduces the text byte-for-byte;
  `groundable_fields_used` records the source elements. The end-to-end M4→M5→M6 example verifies
  the whole pipeline (grounding `verified=true`, zero violations).

---

## M7 — Analyst Workspace, Disposition & Routing

Status: complete (pending review). The acceptance loop: composes M4/M5/M6 into a
two-screen analyst product (triage queue → case → disposition → routing) over the
FastAPI online path, consumed by Streamlit. No new fraud/model/explanation logic —
M7 presents and orchestrates, and holds the human-in-the-loop boundary.

### Completed

- **Service layer** (`src/tfm/services/`): `case_service` (assemble+persist a queued
  case; compose the case view; drill-down), `queue_service` (risk-ordered, re-sortable,
  filterable by level/rule/min-amount), `disposition_service` (engagement floor,
  rationale graduation, deviation, routing-as-state-change, **complete audit snapshot**),
  and typed `errors` mapped to the uniform API error body (Addendum §2.5).
- **API** (`src/tfm/api/`): `schemas.py` (the composed `CaseView` embedding the M4
  `EvidencePackage`, M5 `Recommendation`, M6 `Explanation` verbatim; `QueueResponse`;
  disposition request/response) and routes `GET /api/queue`, `GET /api/cases/{id}`,
  `GET /api/cases/{id}/evidence/{element_id}`, `POST /api/cases/{id}/disposition`,
  `GET /api/cases/{id}/audit`; uniform error handler.
- **Workspace** (`src/tfm/web/`): `render.py` (pure, tested — analyst-language mapping:
  "Risk Indicators Detected", "Decision Basis", the no-default disposition control) and
  `app.py` (two-screen Streamlit: queue with filter/sort; case with the What happened →
  Recommended Action → Why this case → Risk Indicators → Your decision hierarchy).
- **Demo seed** (`scripts/seed_cases.py`): curated cases so the queue opens on strong,
  legible fraud stories (account-draining escalates first), with honest thin holds present.
- **Persistence**: `cases.score` made nullable (model + migration `0002`, batch mode for
  SQLite/Postgres) — the FR-4 absent-score stored honestly as `NULL` / `score_band="none"`.
- **Explanation copy** refined to an analyst-assistant tone (`explanation/templated.py`,
  copy-only; still grounded by construction, gate still passes).

### Analyst-experience decisions (M7 product lens)

- **Recommended Action is the dominant element**; **Decision Basis** is supporting context.
- **Graceful degradation reads as a governance feature**: within the Recommended Action area,
  "Model scoring is excluded by the leakage gate — this case is assessed on verified rule
  evidence." Legible and unmissable, not a top banner, not a blank.
- **Human decision boundary**: disposition renders with **no default** (`index=None`, verified
  on Streamlit 1.58) + sentinel + submit-disabled-until-chosen; the recommendation reads as an
  input to weigh; deviation is frictionless and logged.
- **Traceability**: every risk indicator expands to its raw signal (drill-down); the UI surfaces
  the existing M4/M6 provenance, no explanation logic re-implemented.

### Traceability

FR-13, FR-14, FR-15, FR-16, FR-17, FR-18, FR-19, FR-20; NFR-4; §11.2; Addendum §2.3–2.5, §4;
Principle: Human in the Loop, No Automated Blocking, Layer Separation, Audit.

### Verification

`tests/unit/test_workspace.py` (16) + `tests/unit/test_api_workflow.py` (6) — case composition &
drill-down; queue ordering + filters; engagement floor; escalate/deviation rationale; routing +
**no auto-execution**; `409` on re-disposition; **complete audit snapshot at write time** (all
FR-20 fields asserted); render helpers incl. no-default disposition; full API loop via TestClient
incl. the graceful-degradation `200`/templated contract. Demo seed smoke-run produces 2 escalate +
3 hold cases, escalates first. Full suite: **237 passed**; Ruff + `ruff format --check` + mypy clean.

### Assumptions / Deviations

- Queue filtering is applied in memory (curated demo scale); JSON-column querying deferred if
  scaled (BL-M7-01).
- Search/filter kept to a minimal queue filter (FR-19) per the Release Plan; broader search is B9.
- Explanation copy reworded (copy-only); the two M6 wording assertions updated accordingly.

### Implementation Concerns

- None. (`cases.score` nullable was pre-approved.)

### Backlog

- BL-M7-01: push queue filtering into indexed columns / SQL if the queue scales.
- BL-M7-02: full-text search over transactions (Release Plan B9, FR-19); workspace polish (B10).
- BL-M7-03: full audit-event coverage + reconstruct-from-log-alone integration test (M8).

---

## M7 — Implementation Summary

- **Composed case, boundaries preserved**: `CaseView` embeds the M4 `EvidencePackage`, M5
  `Recommendation`, and M6 `Explanation` verbatim as separate sections; the workspace renders them
  as What happened → Recommended Action → Why this case → Risk Indicators → Your decision.
- **Human decision boundary held**: disposition renders unselected (`index=None`, tested); the
  recommendation is advisory input; routing is a state change only — nothing auto-executed.
- **Graceful degradation as a feature**: the excluded scorer is surfaced within Recommended Action
  as an intentional governance mode ("assessed on verified rule evidence"), never a blank or error.
- **Evidence traceability**: each risk indicator drills down to its raw signal; provenance is
  surfaced, not recomputed.
- **Audit complete at write time**: the `disposition_recorded` record carries the full decision
  snapshot (evidence shown, score status, recommendation, disposition + rationale + deviation,
  explanation pathway, identity, timestamp) — asserted by a completeness test.
- **Demo-ready**: `scripts/seed_cases.py` opens the queue on strong cases; the ~3-minute judge
  walkthrough (queue → open → review → drill → decide → justify → route → audit) runs end to end.
