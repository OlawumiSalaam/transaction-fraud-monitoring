# Version 1 — Hackathon Artifact Archive

This directory archives the presentation and submission materials produced for the Version
1 hackathon submission (`v1.0.0`).

It exists so that a reader can find the V1 materials, and — just as importantly — so that
the artifacts which *must not* be moved here are documented as such.

---

## Currently archived

Nothing yet.

The V1 hackathon deck and submission package were produced **outside the repository** (the
`README.md` presentation link points to an external Google Slides deck). No slide file,
submission document, or presentation export has ever been tracked in git.

If those materials are added to the repository later, this directory is where they belong.
Suggested naming:

```
docs/archive/v1-hackathon/
├── README.md            this file
├── slides.pdf           hackathon presentation deck (export)
└── submission.md        submission write-up, as submitted
```

---

## What is deliberately *not* archived here

### Evaluation reports — they stay under `evaluation/reports/`

The V1 evaluation artifacts are **not documentation**. They are live artifacts wired into
running code, and moving them would break the build:

| Artifact | Consumed by |
|---|---|
| `evaluation_manifest.json` | `scripts/package_evaluation.py` — the single source of truth for packaging; it resolves artifact paths from this file rather than from hardcoded filenames |
| `evaluation_summary.json` | `tests/unit/test_evaluation.py` — asserts the headline metrics match the committed M2 artifact verbatim |
| `leakage_verdict.json` | `evaluation/run_all.py` — read verbatim, not regenerated |
| `tfm-scorer-*_training_report.json` | the per-model-version training record; the evidence base for the leakage verdict |

`python -m evaluation.run_all` also regenerates three of these **in place**. Relocating any
of them would silently break the manifest contract, the packaging check, and the evaluation
test.

They remain at `evaluation/reports/`, where they are cited from
[`../../V1_RETROSPECTIVE.md`](../../V1_RETROSPECTIVE.md) and
[`../../../PROJECT_CONTEXT.md`](../../../PROJECT_CONTEXT.md).

### Design records — they stay under `docs/internal/`

The product specification, engineering addendum, delivery plans, conventions, and the
implementation decision/progress/traceability logs are retained under `docs/internal/` for
provenance. They are still the authoritative record of *why* V1 is shaped the way it is,
and several are actively referenced by the V2 execution plan (DDR-01, IMP-005, IC-M3-01,
BL-M8-01). They are not historical artifacts to be boxed up.

### Engineering documentation — it stays live

`docs/PROJECT_DOCUMENTATION.md`, `PROJECT_CONTEXT.md`, `CHANGELOG.md`, and
`docs/V1_RETROSPECTIVE.md` describe the currently deployed system. They are maintained
documents, not archive material.

---

## Where the V1 materials actually live

| Material | Location |
|---|---|
| Hackathon deck | External (Google Slides) — see the presentation link in `README.md` |
| Submission write-up | External; not tracked in this repository |
| Live demo (workspace) | https://transaction-fraud-monitoring.streamlit.app/ |
| Live API | https://transaction-fraud-monitoring.onrender.com/docs |
| Evaluation evidence | `evaluation/reports/` (see above — do not move) |
| Screenshots used in the submission | `docs/images/` |
| The tagged V1 source | git tag `v1.0.0` |
| The engineering story | `docs/V1_RETROSPECTIVE.md` |
