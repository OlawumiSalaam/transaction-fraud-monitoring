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

Milestone **M0 — Project Bootstrap**: complete. This establishes structure,
typed configuration, dependency management, environment strategy, structured
logging, database migrations, the audit-writer scaffold, the CI skeleton, and
development conventions. **No architectural business logic is implemented yet.**
Layers are built one milestone at a time (M1–M10) per the Implementation Plan.

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
