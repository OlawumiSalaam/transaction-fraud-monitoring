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

## Run the whole stack (reproducible)

```bash
cp .env.example .env
docker compose up --build
```

This starts Postgres, applies migrations, serves the API on `:8000`, and runs the
Streamlit workspace on `:8501`. The LLM is disabled by default, so the stack runs
on the templated pathway (the graceful-degradation floor) until a provider is
configured.

- API health: <http://localhost:8000/health>
- Workspace: <http://localhost:8501>

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
