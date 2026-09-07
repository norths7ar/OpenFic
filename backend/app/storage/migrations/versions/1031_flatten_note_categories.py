"""flatten note categories to one level

Revision ID: 1031
Revises: 1030
Create Date: 2026-09-06 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1031"
down_revision: str | Sequence[str] | None = "1030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE note_categories SET parent_id = NULL WHERE parent_id IS NOT NULL"))


def downgrade() -> None:
    # The previous hierarchy cannot be reconstructed after it has been flattened.
    pass
