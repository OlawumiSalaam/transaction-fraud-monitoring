# Implementation Decision Log

This document records implementation-specific engineering decisions made during development of the **Transaction Fraud Monitoring** product.

The product architecture and functional behaviour are governed by the approved design documents. This log records engineering choices made while implementing that design. It does **not** redefine or modify the approved architecture.

---

# Governing Documents

The following documents remain the authoritative source of truth, in order of precedence:

1. Product Specification
2. Engineering Addendum
3. Hackathon Release Plan
4. Long-Term Implementation Plan

If an implementation issue cannot be resolved without changing one of these documents:

- Stop implementation.
- Raise an **Implementation Concern**.
- Do not silently reinterpret the design.
- Do not record architectural changes in this file.

---

# Purpose

This log exists to record engineering decisions that:

- preserve the approved architecture,
- affect implementation,
- are likely to influence future development,
- should be understandable months after the project is completed.

Typical examples include:

- technology selection,
- library selection,
- deployment decisions,
- serialization formats,
- API conventions,
- implementation strategies,
- engineering trade-offs,
- infrastructure choices.

Routine coding decisions, bug fixes, refactoring, formatting, and minor implementation details belong in Git history—not here.

---

# Decision Record Template

Every implementation decision should follow this structure.

## ID

IMP-XXX

## Date

YYYY-MM-DD

## Title

Short descriptive title.

## Status

Proposed | Approved | Superseded

## Context

Describe the implementation problem or constraint that required a decision.

## Decision

Describe what was decided.

## Rationale

Explain why this approach was selected.

## Alternatives Considered

List the main alternatives and why they were rejected.

## Impact

Describe the parts of the system affected.

## Specification Traceability

List the relevant references, for example:

- FR-15
- NFR-4
- §5.5
- Principle: Human in the Loop
- Principle: Canonical Evidence Schema
- M7

---

# Decision Log

---

## IMP-001

**Date**

2026-07-03

**Title**

Streamlit selected as the Version 1 analyst workspace

**Status**

Approved

### Context

The original implementation plan proposed a server-rendered interface using Jinja2 and HTMX.

Given the fixed three-day hackathon delivery window, a faster implementation approach was required without changing the approved product architecture.

### Decision

Use **Streamlit** as the Version 1 analyst workspace.

All business logic remains behind the REST API.

Streamlit functions only as the presentation layer and consumes the backend APIs.

### Rationale

This minimizes frontend engineering effort while preserving:

- architectural layer separation,
- human-in-the-loop decision making,
- interface boundaries,
- future replaceability of the presentation layer.

The presentation technology changes.

The architecture does not.

### Alternatives Considered

**Jinja2 + HTMX**

Rejected for Version 1 because it increases implementation effort without improving the behaviour evaluated by the hackathon.

### Impact

Affected components:

- Analyst Workspace
- UI Layer

Unaffected components:

- Fraud Scoring
- Rule Engine
- Evidence Assembly
- Recommendation Policy
- Grounding Gate
- Audit Log
- REST API
- Persistence
- Data Pipeline

### Specification Traceability

- Engineering Addendum
- Hackathon Release Plan
- M7
- Principle: Layer Separation
- Principle: Human in the Loop

---

## IMP-002

**Date**

2026-07-03

**Title**

Streamlit dependency floor raised to >=1.58 (FR-15 hardening)

**Status**

Approved

### Context

The initial bootstrap declared `streamlit>=1.27`. The non-pre-selected disposition
control (FR-15) is a non-negotiable architectural invariant. Engineering Addendum §1
explicitly verifies that `index=None` on `st.selectbox` / `st.radio` produces no
default selection as of Streamlit 1.58.0.

The installed environment resolves to 1.58.0. Relying solely on the lock file means
any fresh environment that installs without the lock (e.g., a clean pip install from
pyproject.toml) could resolve to an older version where the invariant is unverified.

### Decision

Raise the Streamlit lower bound in `pyproject.toml` from `>=1.27` to `>=1.58`.

### Rationale

The approved architecture guarantees `index=None` behaviour. The dependency floor
should express that guarantee at the packaging layer, not just rely on a lock file.
This is a post-approval hardening change, not an architectural change.

### Alternatives Considered

**Keep >=1.27 and rely on uv.lock** — rejected because the lock file is not present
in all install paths (e.g., pip, other package managers), and the invariant is
architectural.

### Impact

Affects: packaging only.
Unaffected: all business logic, architecture, API contracts, schema.

### Specification Traceability

- FR-15 (disposition control — no default selection)
- Engineering Addendum §1 (Streamlit index=None verification)
- Principle: Disposition Control

---

## IMP-003

**Date**

2026-07-03

**Title**

pandas and numpy promoted from [ml] extras to base dependencies

**Status**

Approved

### Context

The original pyproject.toml placed `pandas>=2.2` and `numpy>=1.26` in the `[ml]`
optional-dependency group alongside scikit-learn and lightgbm. CI installs
`.[dev]` (base + dev extras) and does not install `[ml]`. The M1 data pipeline
(ingest, features, splits) depends on pandas and numpy but is not ML-specific: it
is core infrastructure used by the ingestion path, the feature builder, and the
OOT split — all of which need to be tested in CI.

### Decision

Move `pandas>=2.2` and `numpy>=1.26` from `[project.optional-dependencies].ml`
to `[project.dependencies]` (base). scikit-learn and lightgbm remain in `[ml]`.

### Rationale

pandas and numpy are infrastructure for the data layer, not ML-specific tools.
Keeping them in `[ml]` would silently exclude them from CI without the `[ml]`
extra, causing M1 test failures in the standard install path.

### Alternatives Considered

**Add `[ml]` to CI install** — rejected because it would also pull scikit-learn
and lightgbm into CI before M2, and the `[ml]` group is intended for the scorer
which is not implemented until M2.

### Impact

Affects: packaging and CI install path.
Unaffected: all business logic, architecture, API contracts, schema.

### Specification Traceability

- FR-1 (canonical data pipeline)
- §6.5 (feature computation)
- NFR-3 (reproducibility)

---

## IMP-004

**Date**

2026-07-03

**Title**

bal_dest_before and bal_dest_after excluded from FEATURE_COLUMNS; imputation deferred to M2 scorer

**Status**

Approved

### Context

PaySim merchant destinations (counterparty_id prefixed with 'M') produce no
destination-balance signal: the simulator does not model merchant internal balances.
These rows have `bal_dest_before = None` and `bal_dest_after = None` after ingestion
(R1 guard, Addendum §4).

Both fields are present in the canonical `Transaction` entity, in the ingest output
DataFrame, and in the `FeatureVector` — they carry real signal for non-merchant
counterparties (e.g., mule-passthrough detection). However, including them directly
in `FEATURE_COLUMNS` would force the feature builder to choose an imputation strategy
for merchant rows, which is a scorer concern, not a feature-engineering concern.

### Decision

`bal_dest_before` and `bal_dest_after` are:
- Preserved in the canonical schema, the ingest DataFrame, and the FeatureVector
  (no information loss).
- Excluded from `FEATURE_COLUMNS` (the list shared by the ML scorer as its input
  matrix).

The M2 scorer owns the imputation strategy (e.g., zero-fill for merchants, or
dropping the columns from non-merchant-only transaction types).

### Rationale

The feature builder's responsibility is to produce interpretable, point-in-time
features. Deciding how to handle structural None values in a class-conditional
fashion requires knowledge of which model(s) are being trained and which
transaction types they target — both of which are M2 concerns.

Keeping the fields in the FeatureVector ensures the rule engine (FR-6 —
mule_passthrough rule) and the evidence assembler (M4) can reference them for
peer transactions without any imputation.

### Alternatives Considered

**Zero-impute at build_features time** — rejected because imputing 0 for
merchant-destination balance columns would assign a misleading numeric signal and
could introduce leakage-adjacent confounding; this decision belongs to the scorer
preprocessing pipeline.

**Drop from FeatureVector entirely** — rejected because the rule engine
(mule_passthrough) and the evidence assembler require the raw balance values for
peer transactions.

### Impact

- `FEATURE_COLUMNS` does not contain `bal_dest_before` or `bal_dest_after`.
- M2 scorer must decide: drop columns, impute, or restrict to non-merchant rows.
- FeatureVector and canonical schema: unchanged.

### Specification Traceability

- FR-5 (shared feature substrate)
- FR-6 (mule_passthrough rule — requires dest balance signal for peer transactions)
- §6.5 (feature strategy)
- R1 (merchant balance guard, Addendum §5)
- Principle: Canonical Evidence Schema

---

## IMP-005

**Date**

2026-07-03

**Title**

Point-in-time property tests: shared sliding-window traversal proven once; distinct set-accumulation traversal proven separately

**Status**

Approved

### Context

`build_features` calls `_account_features` per account group, which implements two
distinct sub-mechanisms inside a single `for i in range(n)` loop:

**Mechanism A — 24 h sliding window** (`txn_count_24h`, `amount_sum_24h`):
Uses a shared `lo` pointer, `window_count`, and `window_sum` managed by identical
add (`if i > 0`) and evict (`while lo < i and timestamps[lo] < cutoff`) logic.
At the point where `txn_count_24h[i]` and `amount_sum_24h[i]` are assigned, both
read from the same window state in the same iteration.

**Mechanism B — set accumulation** (`is_new_counterparty`, `distinct_counterparties_seen`):
Uses a shared `seen_cps` set that is read (for both values) before being mutated
(`seen_cps.add(cp)`). At row i, `seen_cps` contains exactly counterparties from
rows 0..i-1. Both fields read from the same set state before any mutation.

The two mechanisms are distinct: Mechanism A is time-bounded (evicts rows >24h);
Mechanism B is unbounded accumulation (no eviction). They share only the outer
loop's `j < i` positional invariant.

### Decision

- Mechanism A is covered by a single Hypothesis property test
  (`test_features_point_in_time_invariant`) that verifies `txn_count_24h`.
  `amount_sum_24h` is not tested separately because it reads from the identical
  `window_sum` state; correctness of `txn_count_24h` (i.e., `window_count` is
  right) implies correctness of `amount_sum_24h` (i.e., `window_sum` is right)
  since both are updated and evicted by the same lines.

- Mechanism B is covered by a second Hypothesis property test
  (`test_features_counterparty_prior_transactions_invariant`) that verifies both
  `is_new_counterparty` and `distinct_counterparties_seen` against the same
  ground-truth (the set of prior counterparty_ids for each account group), since
  both features read from the same `seen_cps` state.

### Rationale

Re-testing `amount_sum_24h` with a separate property test would test the same
sliding-window pointers a second time. The shared-mechanism argument is valid and
bounded: if the window state is wrong, `txn_count_24h` would already fail. Separate
tests add noise without additional coverage of distinct traversal code.

The counterparty traversal is different — it is a set lookup with no time bound
— so it requires its own invariant-level verification.

### Impact

- `tests/unit/test_features.py`: two Hypothesis property tests, one per mechanism.
- No code changes to the feature builder.

### Standing Engineering Rule

**Any future history-dependent feature added to `_account_features` or any successor function must either:**

1. **Reuse an already-verified traversal mechanism** — in which case it inherits the existing property-test coverage and must be documented as sharing Mechanism A (sliding window) or Mechanism B (set accumulation), or
2. **Introduce its own invariant-level property test** — if it requires a new temporal traversal (e.g., a different window width, a different eviction policy, or an unbounded accumulation over a different key).

Deterministic unit tests alone are not sufficient to demonstrate the point-in-time invariant for a feature with a new traversal mechanism. The property test must exercise the boundary — no feature at row i may read data from row j ≥ i — across a sufficiently large sample of randomly generated account histories.

This rule applies regardless of how simple the new feature appears. Simplicity does not imply correctness of temporal boundary enforcement; shared mechanism does.

### Specification Traceability

- FR-5 (shared feature substrate — invariants shared across consumers)
- §6.5 (point-in-time features)
- R2 (temporal leakage guard, Addendum §5)
- Implementation Plan §10 (property-based testing requirement)

---

## IMP-006

**Date**

2026-07-03

**Title**

Candidate-specific preprocessing occurs inside training pipelines; the canonical M1 feature dataset is immutable

**Status**

Approved

### Context

The three M2 candidates require different preprocessing:

- **HistGradientBoosting** (primary) handles `NaN` natively; no imputation is required.
- **LightGBM** (kitchen-sink comparator) consumes the augmented feature set, which
  includes `bal_dest_before` / `bal_dest_after`; these are zero-imputed for merchant
  rows (the imputation deferred in IMP-004, resolved here for the comparator only).
- **Logistic regression** (floor) requires imputation of every `NaN` plus feature
  standardisation (`StandardScaler`).

If preprocessing mutated the shared feature dataset produced by M1's `build_features`,
the three candidates would contend over a single representation, and the canonical
substrate consumed by the rule engine (M3) and evidence assembler (M4) could drift to
match a modelling convenience — a layer-separation violation.

### Decision

- `build_features` (M1) produces the single canonical feature dataset. It is never
  mutated by any M2 code. All M2 functions that consume it operate on a defensive
  copy of the columns they need (`df[cols].copy()`), never in place.
- Each candidate owns its preprocessing (imputation, scaling, feature-set selection)
  entirely inside its own training pipeline (`ml/preprocess.py`, `ml/candidates.py`).
  Preprocessing transforms are fitted on the training split only and applied to the
  validation and test splits (no cross-split fitting).
- The canonical dataset and `FEATURE_COLUMNS` remain the authority. Candidate-specific
  representations are private to the modelling layer and are not written back.

### Rationale

The canonical substrate is shared verbatim by the scorer, the rule engine, and the
evidence assembler (§6.5, FR-5). Preprocessing is a modelling concern local to a
single candidate; it must not leak into the shared representation. Keeping the
canonical dataset immutable preserves layer separation and prevents modelling
choices from silently altering what rules and explanations are grounded in.

### Alternatives Considered

**Pre-impute the canonical dataset once for all candidates** — rejected: it would
bake a modelling choice (zero-fill) into the substrate the rule engine and evidence
assembler read, misrepresenting merchant rows as having a real zero destination
balance, and coupling the layers.

### Impact

- `ml/preprocess.py`, `ml/candidates.py`: candidate-private preprocessing.
- `data/features.py` output: unchanged and never mutated by M2.
- Tests assert the input DataFrame is not modified by any preprocessing call.

### Specification Traceability

- FR-5 (shared feature substrate)
- §6.5 (interpretable features; single substrate)
- Principle: Layer Separation
- Principle: Canonical Evidence Schema
- IMP-004 (bal_dest imputation deferral — resolved here for the comparator)

---

## IMP-007

**Date**

2026-07-03

**Title**

The simulator-leakage verdict is evidence-based; numeric thresholds are configurable decision-support defaults, not the definition of the decision

**Status**

Approved

### Context

The simulator-leakage gate (FR-26, §9) determines whether a model has learned
behavioural fraud patterns or merely bookkeeping (balance-consistency) artefacts.
An early framing expressed the verdict as a single numeric threshold on the
ablation delta (e.g., "pass if ΔPR-AUC ≤ 0.10"). That framing risks reducing an
architectural eligibility decision to one tunable constant.

### Decision

The verdict is **evidence-based**. The gate assembles and records a body of
evidence:

1. **Ablation delta** — the change in behavioural performance (PR-AUC, and
   supporting metrics) when the balance-artifact features are removed.
2. **Feature-importance inspection** — permutation importances of the full model,
   showing whether balance-artifact features dominate.
3. **Remaining behavioural performance** — the ablated model's absolute
   performance, showing whether genuine behavioural signal remains without the
   artefacts.

The verdict (`pass` / `fail`) is derived from this evidence taken together. Any
numeric thresholds (ablation-delta ceiling, minimum remaining PR-AUC, importance
concentration) live in `config/model.yaml` as **configurable engineering defaults
that support the decision**. They are recorded with the verdict as the basis, but
they do not by themselves define eligibility: the recorded evidence and rationale do.

The `LeakageVerdict` artefact therefore carries: the verdict, the full evidence,
the configured defaults applied, and a human-readable rationale.

### Rationale

FR-26 requires a *reported, gating result* established via feature-importance
inspection and ablation with a documented conclusion. Presenting the verdict as
evidence with decision-support defaults — rather than a lone threshold — matches
the specification's intent (§9), keeps the engineering judgement transparent and
auditable, and lets a reviewer disagree with a default without the gate silently
flipping.

### Alternatives Considered

**Single hard threshold on ablation delta** — rejected: reduces an architectural
decision to one constant, hides the reasoning, and is brittle to dataset scale.

### Impact

- `evaluation/leakage_gate.py`: returns a `LeakageVerdict` carrying verdict +
  evidence + applied-defaults + rationale.
- `config/model.yaml`: `leakage_gate` defaults are decision-support parameters.
- `model_versions.leakage_verdict` stores the verdict; the evidence is stored in
  `model_versions.df1_result` / the evaluation report artefacts.

### Specification Traceability

- FR-4 (eligibility gated by the leakage validation)
- FR-26 (simulator-leakage validation is a reported, gating result)
- §9 (simulator learnability; feature-importance + ablation + documented verdict)
- M2 fixed decision (the gate does not flex)

---

## IMP-008

**Date**

2026-07-03

**Title**

CI installs the `[ml]` extra from M2 onward; offline evaluation code lives in a root `evaluation/` package added to mypy and pytest

**Status**

Approved

### Context

M2 introduces the scorer, calibration, and the leakage gate, which depend on
scikit-learn and LightGBM (declared in the `[ml]` optional-dependency group). The
CI quality job installed `.[dev]` only, which excludes `[ml]`, so M2 modules and
their tests would not import in CI. Separately, the Implementation Plan (§7) places
the offline evaluation modules (`model_eval.py`, `leakage_gate.py`,
`calibration_report.py`) in a root-level `evaluation/` directory, outside
`src/tfm/`, which the existing mypy (`files = ["src/tfm"]`) and pytest
(`pythonpath = ["src"]`) configuration does not cover.

### Decision

- CI quality job installs `.[dev,ml]` so the ML stack is present for type-checking
  and tests from M2 onward. (The migrations job, which needs no ML, still installs
  the base package only.)
- The offline evaluation package is created at repository root as `evaluation/`
  (per Implementation Plan §7). `evaluation` is added to `[tool.mypy].files` and to
  `[tool.pytest.ini_options].pythonpath` so it is strictly type-checked and
  importable in tests. Produced report artefacts are written under
  `evaluation/reports/`.

### Rationale

The ML stack is genuinely required from M2; the `[ml]` extra exists for exactly
this boundary. Keeping the evaluation modules at repository root honours the
approved layout (§7) while the tooling updates ensure they receive the same strict
type-checking and test coverage as the rest of the codebase — appropriate given the
leakage gate is credibility-critical.

### Alternatives Considered

**Promote scikit-learn/LightGBM to base dependencies** — rejected: they are heavy
and genuinely ML-specific; the `[ml]` boundary is correct. **Place evaluation code
under `src/tfm/evaluation/`** — rejected in favour of the approved §7 layout;
tooling was extended instead.

### Impact

- `.github/workflows/ci.yml`: quality job installs `.[dev,ml]`.
- `pyproject.toml`: mypy `files` and pytest `pythonpath` include `evaluation`.
- New `evaluation/` package with `reports/` output directory.

### Specification Traceability

- FR-3, FR-22, FR-23, FR-26 (scorer, metrics, calibration, leakage gate)
- Implementation Plan §7 (repository layout), §8 (CI smoke checks)
- NFR-5 (reproducibility — CI exercises the pipeline)

---

## IMP-009

**Date**

2026-07-03

**Title**

Feature builder computes history-dependent features in a single pass over the globally sorted frame (memory optimisation for full-scale PaySim)

**Status**

Approved

### Context

The first full-scale execution of `build_features` on the complete PaySim dataset
(6,362,620 transactions) exhausted memory and destabilised the host until it
restarted. The point-in-time algorithm was correct; the problem was purely one of
memory behaviour in the implementation.

PaySim's `nameOrig` (canonical `account_id`) is almost entirely unique, so grouping
by account produces on the order of **millions of groups**. The prior implementation
materialised one DataFrame per account group inside a Python list and concatenated
them:

```python
account_groups = []
for _, grp in df.groupby("account_id", sort=False):
    account_groups.append(_account_features(grp.sort_values("event_ts")))  # .copy() inside
df = pd.concat(account_groups).sort_index()
```

At peak this held, simultaneously, the sorted frame, ~millions of per-group
DataFrames (each carrying pandas block-manager and index overhead), and the concat
output — an **O(number-of-accounts)** object-overhead term on top of the row data,
which dominated and drove the machine unstable.

This was discovered during M2 full-scale execution. It is an implementation defect,
not an architectural change: the M1 feature families, the Canonical Evidence Schema,
and the point-in-time invariant (R2) are unchanged.

### Decision

Compute the account-behavioural and counterparty features in a **single linear pass**
over the frame after it is stably sorted by `(account_id, event_ts)`. Per-account
sliding-window and counterparty-set state is reset at each account boundary (detected
by a change in `account_id`, which is contiguous after the sort). Results are written
into four preallocated column arrays and assigned back to the frame. The `groupby`,
the per-group `.copy()`/`.sort_values()`, the accumulator list, and the `pd.concat`
are eliminated. `_account_features` is removed from production code.

Lightweight structured progress logging (`feature_build_start` / `feature_build_progress`
every 500k rows / `feature_build_complete`) was added to the stage so long-running
offline jobs are observable. Logging does not affect feature semantics.

### Rationale

Because the global stable sort already places each account's rows contiguously and in
`event_ts` order, the single pass visits rows in exactly the order the per-group
traversal did — identical ordering, identical tie-breaking, identical arithmetic —
so every engineered feature value is preserved bit-for-bit. Peak memory drops from
O(N) data **plus an O(number-of-accounts) DataFrame-object term** to O(N) with a
small constant (the sorted frame plus a handful of column-width arrays). On the full
6.36M-row dataset the stage now completes in ~90 s with stable memory, and the M2
training pipeline (including the simulator-leakage gate) runs to completion.

### Alternatives Considered

**Keep `groupby` but stream results into preallocated arrays (no list, no concat)** —
rejected: it removes the concat copy but still pays per-group DataFrame
materialisation and per-group sorts across millions of groups; the single pass is
simpler and removes the group-count-proportional cost entirely.

**Convert timestamps to numpy `datetime64`/int64 for the window arithmetic** —
deferred: the tz-aware `event_ts` is kept as pandas `Timestamp` objects so the 24 h
lookback arithmetic is byte-for-byte identical to the reference; the remaining
transient allocation is O(N) and bounded, and the observed runtime is acceptable.

### Verification

- `tests/unit/test_features.py`: all 25 tests pass, including both point-in-time
  Hypothesis property tests (R2) and a new equivalence regression test,
  `test_single_pass_matches_grouped_reference`, which asserts identical values for
  every engineered feature column against a **frozen copy of the pre-optimisation
  grouped implementation** on a representative, shuffled multi-account dataset. The
  frozen grouped implementation is retained solely inside the test as a reference
  oracle; production carries a single implementation (no dead code).
- Ruff and mypy clean on `data/features.py`.
- Full PaySim training pipeline (`scripts/train_model.py`) runs end-to-end on all
  6,362,620 rows with exit code 0 and no crash.

### Impact

- `src/tfm/data/features.py`: `build_features` rewritten single-pass;
  `_account_features` removed; progress logging added.
- `tests/unit/test_features.py`: equivalence regression test + frozen reference oracle.
- `build_features` output (values, row order, index), `FEATURE_COLUMNS`, the
  Canonical Evidence Schema, and all downstream consumers: unchanged.

### Specification Traceability

- FR-5 (shared feature substrate)
- §6.5 (point-in-time interpretable features)
- R2 (temporal leakage guard, Addendum §5)
- NFR-5 (reproducibility — full-scale run now completes)
- IMP-005 (point-in-time property tests; the standing rule already anticipates a
  "successor function" to `_account_features`)
- Principle: Data Integrity (feature computation is point-in-time)

---

## Future Decisions

Additional implementation decisions will be recorded here as they are approved.

Examples may include:

- LLM provider selection
- Model serialization strategy
- Container deployment decisions
- API versioning strategy
- Data storage optimizations
- Streaming integration strategy (Kafka)
- Caching strategy (Redis)
- Model registry implementation