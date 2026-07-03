# Development Conventions

The working agreement for implementing the Transaction Fraud Monitoring product.
Implementation follows the approved specification; it does not reinterpret it.

## Milestone workflow

The project progresses one milestone at a time. For each milestone:

1. Implement only the scope defined for that milestone.
2. Keep every implementation traceable to the specification (see below).
3. Surface implementation concerns separately from design concerns.
4. Provide the relevant code, tests, documentation, and a brief implementation summary.
5. Identify any deviations or assumptions explicitly.
6. Pause for review before moving to the next milestone.

## Traceability

Every significant behaviour cites its source in the specification, plan, or
addendum, in the code (docstring) and in the pull request. A behaviour that
cannot cite a requirement is not built. Tags: `[FR-n]`, `[NFR-n]`, `[P:...]`,
`[A:...]`, `[DF-n]`, `[§n]`, `[RAI]`.

## Architectural invariants (non-negotiable)

These are enforced in code, not by convention, and never relaxed for convenience:

- **No layer collapse.** The ML layer never decides; the policy layer never
  scores; the LLM never scores or decides; only the human disposes.
- **Grounding gate is deterministic code, never a model.**
- **Audit log is append-only.** No update or delete of audit records.
- **Disposition control is never pre-selected.** Structural, not a setting.
- **Rationale engagement floor.** No disposition — including a routine Clear —
  is recorded without at least a structured reason code. A one-click clear is
  impossible. Enforced in the Disposition Service and a database `NOT NULL`
  constraint; `governance.yaml` tunes only the depth above the floor.
- **Point-in-time features and out-of-time splits only.** Random splits are
  prohibited (temporal-leakage guard).
- **Balance-artifact features are quarantined** behind the ablation and the
  simulator-leakage gate; never shipped without the gate's recorded verdict.
- **Configuration is architecture.** No threshold, rule parameter, or ordering
  weight is hardcoded; all live in versioned config.
- **Graceful degradation.** From M6 onward the system runs fully with the LLM
  disabled; LLM failure never surfaces as an error to the analyst.

If implementation reveals a conflict with the specification, stop and raise an
implementation concern. Do not silently change the design.

## Coding standards

- Python 3.11+, full type hints. `mypy` strict passes.
- `ruff` for lint and format. No hand-formatting debates.
- Public interfaces carry a docstring citing the requirement they implement.
- Pydantic v2 for the canonical schema and config; SQLAlchemy 2.0 typed models
  for persistence; domain and persistence models kept separate.
- Deterministic logic (rules, policy, grounding gate) is written as pure
  functions with no I/O, so it is property-testable.
- Configuration via pydantic-settings; secrets via environment only.
- Application logging is structured and separate from the audit log.

## Branching and commits

- `main` is protected and always green.
- Work on short-lived `milestone/M<n>-<slug>` branches; smaller feature branches
  fork from the milestone branch and squash-merge back via PR.
- Conventional commits. PRs name the requirements they satisfy.
- Tag at each milestone (`v0.M1`, `v0.M2`, …).

## Testing

- Unit tests per deterministic component; property tests (Hypothesis) for
  invariants (grounding gate never passes ungrounded tokens; policy total over
  all inputs; features never read a future row).
- Golden/scripted workflow fixtures are QA artifacts, strictly excluded from any
  training or evaluation data.
- Integration tests for the online path, the LLM-disabled path, and audit
  reconstructability.
- Coverage target ≥ 90% on the core deterministic layers.

## Definition of Done (every milestone)

- Typed and lint-clean; `mypy` and `ruff` pass in CI.
- New deterministic logic has unit and, where applicable, property tests.
- Every new behaviour cites a spec reference in its docstring and PR.
- No governance parameter is hardcoded; all in versioned config.
- The system still runs with the LLM disabled (from M6 onward).
- CI is green; the milestone is tagged.
- Any offline-evaluation artifact the milestone produces is reproducible from a
  single command.
