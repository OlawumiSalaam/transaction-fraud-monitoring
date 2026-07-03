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
- **FeatureVector** (`src/tfm/schema/evidence.py`): shared feature substrate used verbatim
  by ML scorer (M2), rule engine (M3), and evidence assembler (M4) — per §6.5, FR-5.
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

### Implementation Concerns

None.

### Backlog

- BL-M2-01: Full bounded hyperparameter comparison / tuning (Release Plan B3).
- BL-M2-02: Per-instance signal attribution (e.g. SHAP) behind the same `ContributingSignal`
  interface, if richer explanations are required (currently global importances + direction).
- BL-M2-03: Commit the PaySim-trained scorer artifact and wire it into `docker compose` (M10).
- BL-M2-04: Subgroup / false-positive-burden analysis (FR-25) — consolidated in M9.