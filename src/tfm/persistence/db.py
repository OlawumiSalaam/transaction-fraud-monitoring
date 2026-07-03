"""Database engine and session management.

Infrastructure only. The relational models live in ``models.py`` and map to the
Canonical Evidence Schema (Addendum §3). No query or business logic lives here.
Postgres backs the running app; SQLite backs the unit-test suite via one common
data-access layer.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from tfm.config.settings import Settings


def create_db_engine(settings: Settings) -> Engine:
    """Create a SQLAlchemy engine from settings."""

    connect_args: dict[str, object] = {}
    if settings.database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    return create_engine(settings.database_url, future=True, connect_args=connect_args)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Transactional session scope: commit on success, roll back on error."""

    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
