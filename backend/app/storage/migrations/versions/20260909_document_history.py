"""Persistent document history and recycle bin."""

from alembic import op

from app.storage.migrations.history_v1 import install, uninstall

revision = "20260909"
down_revision = "20260908"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    connection.exec_driver_sql("""CREATE TABLE document_history (
      id VARCHAR NOT NULL PRIMARY KEY, project_id VARCHAR NOT NULL,
      document_id VARCHAR NOT NULL, kind VARCHAR NOT NULL, title VARCHAR NOT NULL,
      content VARCHAR NOT NULL, source VARCHAR NOT NULL, created_at DATETIME NOT NULL
    )""")
    connection.exec_driver_sql("""CREATE TABLE document_trash (
      id VARCHAR NOT NULL PRIMARY KEY, project_id VARCHAR NOT NULL,
      document_id VARCHAR NOT NULL, kind VARCHAR NOT NULL, title VARCHAR NOT NULL,
      content VARCHAR NOT NULL, payload VARCHAR NOT NULL, deleted_at DATETIME NOT NULL
    )""")
    for table in ("document_history", "document_trash"):
        for column in ("project_id", "document_id"):
            connection.exec_driver_sql(f"CREATE INDEX ix_{table}_{column} ON {table} ({column})")
    install(connection)


def downgrade():
    connection = op.get_bind()
    uninstall(connection)
    connection.exec_driver_sql("DROP TABLE document_trash")
    connection.exec_driver_sql("DROP TABLE document_history")
