# Traceability Matrix

Final traceability audit (M10): every implemented behaviour mapped to its governing
requirement / principle, its implementation, and the test(s) that cover it. Deferred
items are listed at the end with their backlog reference.

Precedence of governing documents: Product Specification → Engineering Addendum →
Hackathon Release Plan → Long-Term Implementation Plan.

## Functional requirements

| Req | Requirement | Implementation | Tests |
|-----|-------------|----------------|-------|
| FR-1 | Canonical Evidence Schema; point-in-time features | `schema/entities.py`, `schema/evidence.py`, `data/features.py` | `test_schema.py`, `test_features.py` |
| FR-2 | Evidence assembly (groundable set) | `assembly/assembler.py` | `test_assembler.py` |
| FR-3 | Fraud scoring from a bounded candidate comparison | `ml/candidates.py`, `ml/pipeline.py`, `ml/train.py` | `test_candidates.py`, `test_train.py`, `test_model.py` |
| FR-4 | Leakage-gated eligibility; a failing model is excluded | `ml/train.py`, `ml/registry.py`; absent-score path in `recommendation/policy.py`, `assembly/assembler.py` (score_signal) | `test_train.py`, `test_recommendation.py`, `test_assembler.py` |
| FR-5 | Interpretability framework (DF-1) | `ml/candidates.py`, `ml/preprocess.py` | `test_candidates.py`, `test_preprocess.py` |
| FR-6 | Deterministic rule engine (auditable if-then) | `rules/engine.py`, `rules/definitions.py` | `test_rules.py` |
| FR-7 | Dormant-account reactivation out of V1 (no proxy) | documented; not implemented | — (documented deferral) |
| FR-9 | Score bands → recommendation | `config/thresholds.yaml`, `recommendation/policy.py` | `test_recommendation.py` |
| FR-10 | Explainer interface | `explanation/explainer.py` | `test_explanation.py` |
| FR-11 | Grounding gate; ungrounded rate ≈ 0 | `explanation/grounding.py`, `evaluation/grounding_report.py` | `test_explanation.py`, `test_evaluation.py` |
| FR-12 | Templated fallback; LLM optional | `explanation/templated.py`, `explanation/explainer.py`, `explanation/llm_explainer.py` | `test_explanation.py`, `test_end_to_end.py` |
| FR-13 | In-interface disclosure: AI-labelling + synthetic data | `web/app.py`, `web/render.py`, disclosure element in `assembly/assembler.py` | `test_workspace.py`, `test_assembler.py` |
| FR-14 | Prioritised, re-sortable, filterable queue | `services/queue_service.py`, `api/routes/queue.py` | `test_workspace.py`, `test_api_workflow.py` |
| FR-15 | Evidence drill-down; disposition with no default | `api/routes/cases.py`, `services/case_service.py`, `web/render.py` | `test_workspace.py`, `test_api_workflow.py` |
| FR-16 | Human is the sole decider | `services/disposition_service.py` | `test_workspace.py` |
| FR-17 | Engagement floor + rationale graduation | `services/disposition_service.py`, `persistence/models.py` (reason_code NOT NULL) | `test_workspace.py` |
| FR-18 | Routing as a state change (no financial action) | `services/disposition_service.py` | `test_workspace.py`, `test_end_to_end.py` |
| FR-19 | Minimal queue filter (search deferred) | `services/queue_service.py` | `test_workspace.py` |
| FR-20 | Audit record: full per-case snapshot | `audit/log.py`, `audit/snapshot.py`, `services/disposition_service.py` | `test_workspace.py`, `test_audit_reconstruct.py` |
| FR-21 | Signals captured, not consumed (offline separation) | `audit/`, `evaluation/` (no feedback path) | `test_evaluation.py` (separation), architecture |
| FR-22 | Model metrics (PR-AUC, precision, recall, ROC-AUC) | `evaluation/model_eval.py`, `evaluation/run_all.py` | `test_model_eval.py`, `test_evaluation.py` |
| FR-23 | Probability calibration | `ml/calibration.py`, `evaluation/run_all.py` | `test_calibration.py` |
| FR-24 | Grounding-rate reporting | `evaluation/grounding_report.py` | `test_evaluation.py` |
| FR-26 | Simulator-leakage gate + verdict | `evaluation/leakage_gate.py`, `ml/train.py` | `test_leakage_gate.py`, `test_train.py` |

## Non-functional requirements

| Req | Requirement | Implementation | Tests |
|-----|-------------|----------------|-------|
| NFR-2 | Graceful degradation (LLM disabled → full function) | `explanation/explainer.py` fallback; templated floor | `test_explanation.py`, `test_end_to_end.py` |
| NFR-3 | Any decision reconstructable from the log alone | `audit/snapshot.py`, `audit/reconstruct.py` | `test_audit_reconstruct.py`, `test_end_to_end.py` |
| NFR-5/8 | One data-access layer; SQLite-backed tests | `persistence/db.py`, `persistence/models.py` | `test_migrations.py`, full suite (SQLite) |
| NFR-7 | Security/retention on the audit store — deployment obligation | documented (BL-M8-01); app-level append-only in `audit/log.py` | `test_audit_writer.py` |

## Principles

| Principle | Enforcement | Tests |
|-----------|-------------|-------|
| Layer separation (score / rules / explanation / human) | distinct packages `ml`, `rules`, `explanation`, `services` | per-layer suites |
| Human in the loop; no automated blocking | `services/disposition_service.py` (routing = state change) | `test_workspace.py`, `test_end_to_end.py` |
| Grounding (deterministic, never a model) | `explanation/grounding.py` | `test_explanation.py`, `test_evaluation.py` |
| Audit append-only | insert-only `audit/log.py` (DB-role revoke = BL-M8-01) | `test_audit_writer.py`, `test_audit_reconstruct.py` |
| Data integrity (point-in-time; OOT only) | `data/features.py`, `data/splits.py` | `test_features.py`, `test_splits.py` |
| Honest reporting (measured vs modelled) | `evaluation/labels.py`, `evaluation/run_all.py` | `test_evaluation.py` |
| Disclosure of synthetic data + generated text | assembler disclosure element; `web/` labelling | `test_assembler.py`, `test_workspace.py` |

## Deferred (documented, with backlog reference)

| Item | Reference |
|------|-----------|
| Dormant-account reactivation rule | FR-7 — out of V1 scope, no proxy |
| Full LLM explainer (stub behind the interface) | Release Plan §M6 — `llm_explainer.py` stub |
| Full-text search over transactions | FR-19 / B9 — BL-M7-02 |
| Per-stage audit events | FR-20 / B11 — BL-M8-02 |
| DB-level append-only enforcement + retention | NFR-7 — BL-M8-01 |
| Subgroup / false-positive-burden; threshold sensitivity | FR-25 / B12 — BL-M9-01/02 |
| Offline-path consumption / feedback loop | FR-21 — deferred by design (captured, not consumed) |

## Acceptance-workflow note (M10, IC-M10-01, Option B)

The operational workflow is demonstrated using **curated synthetic transactions
representative of PaySim scenarios**, intentionally selected to exercise the analyst
workflow and ensure a consistent demo. The machine-learning scorer, leakage
validation, and evaluation evidence were produced from the **full PaySim dataset**
during M2 and are packaged as **immutable M9 evaluation artifacts**
(`evaluation/reports/`). The repository intentionally separates the offline
evaluation pipeline from the online operational workflow; that separation is part of
the architecture and remains unchanged.
