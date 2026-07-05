"""cases.score nullable — operational scorer excluded under FR-4

The operational scorer is gate-ineligible (FR-4), so a case carries no model
score: ``cases.score`` is NULL and ``score_band`` is "none". This is the
persistence counterpart of the M4/M5 honest degradation (M7) — no sentinel, no
fabricated score.

Revision ID: a1b2c3d4e5f6
Revises: fed22ea7434d
Create Date: 2026-07-04 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "fed22ea7434d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # batch mode so the ALTER works on SQLite (test DB) as well as Postgres.
    with op.batch_alter_table("cases") as batch:
        batch.alter_column("score", existing_type=sa.Numeric(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("cases") as batch:
        batch.alter_column("score", existing_type=sa.Numeric(), nullable=False)
