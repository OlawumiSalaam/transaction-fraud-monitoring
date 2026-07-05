# Application image for the Transaction Fraud Monitoring online path.
# The same image runs the API (default) and the Streamlit workspace (compose
# overrides the command). Reproducible install via uv against the committed lock.
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# uv provides fast, reproducible dependency resolution.
RUN pip install --no-cache-dir uv

# Dependency layer (cached until pyproject/lock change).
WORKDIR /app

COPY pyproject.toml uv.lock* README.md ./

RUN uv pip install --system .

# Application code and configuration.
COPY src ./src
COPY config ./config
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
# Demo-data seed (composed online path) — needed so `docker compose up` populates
# the triage queue on a clean clone.
COPY scripts ./scripts

ENV PYTHONPATH=/app/src

EXPOSE 8000

# Default: run the API. docker-compose overrides for the web service.
CMD ["uvicorn", "tfm.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
