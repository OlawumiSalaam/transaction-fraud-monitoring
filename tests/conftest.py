"""Shared test fixtures.

Unit tests run against an in-memory SQLite database via the same models and
data-access layer used by the running app, keeping the suite fast and hermetic.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session, sessionmaker

from tfm.config.settings import Settings
from tfm.persistence.db import create_db_engine, create_session_factory
from tfm.persistence.models import Base


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="ci",
        log_format="console",
        database_url="sqlite+pysqlite:///:memory:",
        config_dir="config",
    )


@pytest.fixture
def session_factory(settings: Settings) -> sessionmaker[Session]:
    engine = create_db_engine(settings)
    Base.metadata.create_all(engine)
    return create_session_factory(engine)


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    sess = session_factory()
    try:
        yield sess
    finally:
        sess.close()
