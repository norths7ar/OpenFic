import importlib
from unittest.mock import patch

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

migration = importlib.import_module(
    "app.storage.migrations.versions.1023_add_imported_archive_flag"
)


def test_upgrade_backfills_archive_flag_and_downgrades() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE tasks (id TEXT PRIMARY KEY)"))
        connection.execute(text("INSERT INTO tasks (id) VALUES ('task-1')"))
        operations = Operations(MigrationContext.configure(connection))

        with patch.object(migration, "op", operations):
            migration.upgrade()

        assert connection.execute(
            text("SELECT is_imported_archive FROM tasks WHERE id = 'task-1'")
        ).scalar_one() in (False, 0)

        with patch.object(migration, "op", operations):
            migration.downgrade()
        assert "is_imported_archive" not in {
            column["name"] for column in inspect(connection).get_columns("tasks")
        }

    engine.dispose()
