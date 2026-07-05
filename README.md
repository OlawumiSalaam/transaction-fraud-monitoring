# Transaction Fraud Monitoring

A case investigation workspace that helps a frontline fraud analyst disposition
flagged transactions faster, more consistently, and more defensibly. For each
flagged transaction it produces a risk score, applies deterministic rules,
assembles the evidence behind the alert, generates a grounded plain-language
explanation with a recommended action, and records the analyst's decision, while
keeping every consequential decision under human control. AI supports the
decision; it never makes it.

## Controlled artifacts

These are the authoritative engineering baseline. Changes are raised as
implementation concerns or documented design changes, not ad hoc revisions.

1. Product Specification (Version 1 Design Record)
2. Implementation Plan (Phase 1)
3. Engineering Addendum (Phase 1.1)

## Status

**Build complete through M10 — Final Integration.** Milestones M0–M9 are
implemented (canonical schema and ingestion, the gate-run scorer and leakage
validation, the deterministic rule engine, evidence assembly, the recommendation
policy, the templated explainer with the grounding gate, the analyst workspace and
human-review workflow, audit completion and reconstructability, and the reproducible
offline evaluation pipeline). M10 verifies the whole system integrates: both run
paths, graceful degradation, packaging, the traceability matrix, and reproducibility
from a clean clone. See `PROGRESS.md` for the per-milestone record and
`docs/TRACEABILITY.md` for the requirement → implementation → test matrix.

## Architecture and package map

The reference architecture distinguishes six logical component kinds (§5.1). The
`src/tfm/schema` package is the canonical evidence schema every layer imports.

| Package | Role | Milestone |
|---|---|---|
| `tfm/schema` | Canonical Evidence Schema (the spine) | M1 |
| `tfm/data` | Ingestion, point-in-time features, out-of-time split | M1 |
| `tfm/ml` | Scorer, training, calibration, registry | M2 |
| `tfm/rules` | Deterministic rule engine | M3 |
| `tfm/assembly` | Evidence assembly | M4 |
| `tfm/recommendation` | Deterministic recommendation policy | M5 |
| `tfm/explanation` | LLM explainer, grounding gate, templated fallback | M6 |
| `tfm/queue` | Triage queue ordering | M7 |
| `tfm/web` | Streamlit analyst workspace | M7 |
| `tfm/audit` | Append-only audit log | M0 scaffold / M8 |
| `tfm/api` | FastAPI online-path service | per milestone |
| `tfm/persistence` | Relational models + session management | M0 |
| `tfm/config` | Typed configuration | M0 |
| `tfm/observability` | Structured logging | M0 |
| `evaluation/` | Offline evaluation pipeline (deferred consumption) | M2/M6/M9 |

## Repository structure

Where things live, for someone opening the repository for the first time:

| Directory | Purpose |
|---|---|
| `src/tfm/` | **Product implementation** — the online path and all four architectural layers (schema, data, ml, rules, assembly, recommendation, explanation, services, api, web, audit, persistence, config, observability). |
| `evaluation/` | **Offline evaluation pipeline** — model metrics, leakage gate, calibration, grounding report, and `run_all.py`. Separate from the online path; nothing here feeds back. Artifacts under `evaluation/reports/`. |
| `tests/` | **Tests** — `unit/` (per-layer), `integration/` (end-to-end online loop), `property/` (Hypothesis), `fixtures/`, shared `conftest.py`. |
| `docs/` | **Documentation** — the controlled artifacts (Product Specification, Engineering Addendum, Hackathon Release Plan, Long-Term Implementation Plan), `CONVENTIONS.md`, and `TRACEABILITY.md`. |
| `config/` | **Versioned governance configuration** — thresholds, rule parameters, queue policy, governance knobs (YAML). |
| `migrations/` | **Alembic migrations** — the canonical schema DDL (`0001`) and `cases.score` nullable (`0002`). |
| `models/` | **Committed model artifact** — the pinned, gate-run scorer (`scorer.joblib`). |
| `scripts/` | **Operational scripts** — demo seeding (`seed_cases.py`) and evaluation packaging integrity (`package_evaluation.py`). |
| `notebooks/` | **Exploratory notebooks** — data understanding (not part of the runtime). |
| `data/` | **Local data workspace** — raw/prepared PaySim (gitignored; not committed). |
| `CLAUDE.md` / `PROGRESS.md` | Engineering constitution / per-milestone implementation record. |

## Run the whole stack

The workspace is a two-process app: a FastAPI online-path service and a Streamlit
UI that talks to it over HTTP. Both run paths below launch the full analyst loop —
triage queue → case → recommendation → grounded/templated explanation → evidence
drill-down → disposition with mandatory rationale → routing → audit. The LLM is
disabled by default, so the stack runs on the templated pathway (the
graceful-degradation floor) until a provider is configured.

### Path A — local, SQLite (no Docker) — primary, tested

Runs entirely from the project virtualenv against a local SQLite file. Uses three
env vars and a file database that lives **outside** the repo (nothing lands in
`git status`).

**Terminal 1 — migrate, seed, serve the API on `:8000`:**

```powershell
$env:DATABASE_URL = 'sqlite:///C:/Users/<you>/AppData/Local/Temp/tfm_demo.db'
$env:CONFIG_DIR   = 'config'
$env:LLM_ENABLED  = 'false'

python -m alembic upgrade head          # applies 0001 + 0002 (cases.score nullable)
python scripts/seed_cases.py            # populates the queue: 2 escalate + 3 hold (idempotent)
python -m uvicorn tfm.api.app:app --app-dir src --host 127.0.0.1 --port 8000
```

**Terminal 2 — the Streamlit workspace on `:8501`:**

```powershell
$env:PYTHONPATH   = 'src'                    # so `tfm.web` imports when Streamlit runs the script
$env:API_BASE_URL = 'http://localhost:8000'  # point the workspace at the API above

python -m streamlit run src/tfm/web/app.py --server.port 8501
```

Open <http://localhost:8501>. The seed is idempotent — re-running it prints
"already present — skipping". To reset, delete the SQLite file and re-run the
migrate + seed steps.

### Path B — Docker Compose (containerized)

```bash
cp .env.example .env
docker compose up --build
```

This starts Postgres, and on the `api` service **applies migrations, seeds the demo
queue (idempotent), then serves** the API on `:8000`; the `web` service runs the
Streamlit workspace on `:8501` pointed at the API. `docker compose up` alone
produces a populated queue — no manual seed step. A second `docker compose up`
does not re-seed (the guard skips on the unique `cases.txn_id`).

- API health: <http://localhost:8000/health>
- Workspace: <http://localhost:8501>

**A correct launch (either path):** the triage queue opens with **5 cases, the 2
Escalate on top** (risk-ordered) — CASH_OUT 985,210.50 and TRANSFER 441,423.00
(both `account_draining` + `new_beneficiary_large`) — then a 250,000 TRANSFER hold
and two small PAYMENT holds. An **empty queue means the seed did not run** against
the same database, not an app failure.

The LLM is disabled by default, so the workspace runs on the **templated
explanation** pathway behind the deterministic grounding gate (graceful
degradation, NFR-2) — the full analyst workflow is operational with no LLM.

## Acceptance workflow and evaluation evidence

The operational workflow is demonstrated using **curated synthetic transactions
representative of PaySim scenarios**, intentionally selected to exercise the analyst
workflow and ensure a consistent demo. The machine-learning scorer, leakage
validation, and evaluation evidence were produced from the **full PaySim dataset**
during M2 and are packaged as **immutable evaluation artifacts** under
`evaluation/reports/`. The repository intentionally separates the offline evaluation
pipeline from the online operational workflow.

Regenerate and verify the evaluation evidence:

```bash
python -m evaluation.run_all          # writes evaluation_summary / grounding_report / manifest
python scripts/package_evaluation.py  # verifies every manifested artifact exists (no hardcoded names)
```

The headline reports the scorer's metrics **alongside** the leakage-gate verdict
(**FAIL** → the model is excluded under FR-4); every number is labelled *measured* or
*modelled estimate*. See `evaluation/reports/evaluation_manifest.json` for the
artifact index and `docs/TRACEABILITY.md` for the full requirement → test matrix.

## Local development

```bash
uv pip install --system ".[dev]"    # or: uv sync
ruff check src tests && ruff format --check src tests
mypy
pytest --cov=tfm --cov-report=term-missing
```

Migrations against a local database:

```bash
export DATABASE_URL=postgresql+psycopg://tfm:tfm@localhost:5432/tfm
alembic upgrade head
```

See `docs/CONVENTIONS.md` for the development conventions and Definition of Done.
