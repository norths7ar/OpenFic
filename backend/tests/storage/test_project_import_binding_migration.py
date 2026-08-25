import importlib
from unittest.mock import patch

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

migration = importlib.import_module(
    "app.storage.migrations.versions.1024_add_project_import_bindings"
)


def test_upgrade_enforces_project_isolation_and_downgrades() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys = ON"))
        connection.execute(text("CREATE TABLE projects (id TEXT PRIMARY KEY)"))
        connection.execute(text("INSERT INTO projects (id) VALUES ('p1'), ('p2')"))
        operations = Operations(MigrationContext.configure(connection))

        with patch.object(migration, "op", operations):
            migration.upgrade()

        insert = text(
            "INSERT INTO project_import_bindings "
            "(id, project_id, binding_key, rule_id, source_path, source_anchor, "
            "target_kind, target_id, last_applied_hash, created_at, updated_at) "
            "VALUES (:id, :project_id, 'key', 'rule', 'doc.md', 'H1:Doc', "
            "'note', :target_id, :hash, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        valid_hash = "sha256:" + "0" * 64
        connection.execute(
            insert,
            {"id": "b1", "project_id": "p1", "target_id": "n1", "hash": valid_hash},
        )
        connection.execute(
            insert,
            {"id": "b2", "project_id": "p2", "target_id": "n2", "hash": valid_hash},
        )
        try:
            connection.execute(
                insert,
                {
                    "id": "b3",
                    "project_id": "p1",
                    "target_id": "n3",
                    "hash": valid_hash,
                },
            )
        except IntegrityError:
            pass
        else:
            raise AssertionError("same project accepted a duplicate binding key")

        with patch.object(migration, "op", operations):
            migration.downgrade()
        assert "project_import_bindings" not in inspect(connection).get_table_names()

    engine.dispose()
