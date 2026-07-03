"""Health endpoint test.

Exercises the FastAPI startup lifespan: structured logging, fail-fast config
validation, and the DB session factory. No business routes are asserted at M0.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tfm.api.app import create_app
from tfm.config.settings import get_settings


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("APP_ENV", "ci")
    monkeypatch.setenv("LOG_FORMAT", "console")
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("CONFIG_DIR", "config")
    get_settings.cache_clear()
    return TestClient(create_app())


def test_health_ok(client: TestClient) -> None:
    with client:
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["app_env"] == "ci"
    assert body["config_loaded"] is True
    assert body["db_reachable"] is True
