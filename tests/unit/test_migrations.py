"""Migration smoke test.

Runs ``alembic upgrade head`` against a temporary SQLite database and confirms
the full relational schema is created, then downgrades cleanly. Proves the
migration tooling and the initial schema are wired correctly.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from tfm.config.settings import get_settings

EXPECTED_TABLES = {
    "accounts",
    "counterparties",
    "transactions",
    "model_versions",
    "cases",
    "rule_hits",
    "dispositions",
    "audit_log",
}


def _alembic_config(db_url: str) -> Config:
    os.environ["DATABASE_URL"] = db_url
    get_settings.cache_clear()
    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    return cfg


def test_migration_creates_and_drops_schema() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "mig.db"
        db_url = f"sqlite+pysqlite:///{db_path}"
        cfg = _alembic_config(db_url)

        command.upgrade(cfg, "head")
        engine = create_engine(db_url)
        tables = set(inspect(engine).get_table_names())
        assert EXPECTED_TABLES.issubset(tables)

        command.downgrade(cfg, "base")
        tables_after = set(inspect(engine).get_table_names())
        assert EXPECTED_TABLES.isdisjoint(tables_after)
        engine.dispose()

    get_settings.cache_clear()
