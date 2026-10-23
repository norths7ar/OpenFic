"""Explicit provider catalog adaptation and independently persisted model speed."""

import sqlalchemy as sa
from alembic import op

revision = "20261023"
down_revision = "20261020"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "model_providers",
        sa.Column("catalog_mode", sa.String(20), nullable=False, server_default="generic"),
    )
    op.add_column(
        "models",
        sa.Column("default_speed", sa.String(20), nullable=False, server_default="standard"),
    )
    op.execute("""UPDATE settings SET value = ''
        WHERE key IN ('default_model', 'light_model') AND value != ''
        AND NOT EXISTS (SELECT 1 FROM models WHERE models.id=settings.value
                        AND models.is_enabled=1 AND models.task_type='llm')""")
    op.execute("""UPDATE agent_definitions SET model_id = NULL
        WHERE model_id IS NOT NULL AND model_id NOT IN ('', '__system_default_model__', '__system_light_model__')
        AND NOT EXISTS (SELECT 1 FROM models WHERE models.id=agent_definitions.model_id
                        AND models.is_enabled=1 AND models.task_type='llm')""")


def downgrade():
    op.drop_column("models", "default_speed")
    op.drop_column("model_providers", "catalog_mode")
