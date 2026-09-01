import importlib
from unittest.mock import patch

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

migration = importlib.import_module(
    "app.storage.migrations.versions.1022_add_world_sections_and_task_context_mode"
)


def _create_previous_schema(connection) -> None:
    connection.execute(text("CREATE TABLE world_info_entries (id TEXT PRIMARY KEY)"))
    connection.execute(text("CREATE TABLE revision_world_entry_snapshots (id TEXT PRIMARY KEY)"))
    connection.execute(text("CREATE TABLE tasks (id TEXT PRIMARY KEY)"))
    connection.execute(text("INSERT INTO world_info_entries (id) VALUES ('entry-1')"))
    connection.execute(text("INSERT INTO tasks (id) VALUES ('task-1')"))


def test_upgrade_backfills_section_and_context_mode_and_downgrades() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        _create_previous_schema(connection)
        operations = Operations(MigrationContext.configure(connection))

        with patch.object(migration, "op", operations):
            migration.upgrade()

        entry = connection.execute(
            text("SELECT section FROM world_info_entries WHERE id = 'entry-1'")
        ).scalar_one()
        task = connection.execute(
            text("SELECT context_mode FROM tasks WHERE id = 'task-1'")
        ).scalar_one()
        assert entry == ""
        assert task == "local"
        assert "section" in {
            column["name"]
            for column in inspect(connection).get_columns("revision_world_entry_snapshots")
        }

        with pytest.raises(IntegrityError):
            connection.execute(
                text("INSERT INTO tasks (id, context_mode) VALUES ('task-invalid', 'surprise')")
            )

        with patch.object(migration, "op", operations):
            migration.downgrade()

        assert "section" not in {
            column["name"] for column in inspect(connection).get_columns("world_info_entries")
        }
        assert "context_mode" not in {
            column["name"] for column in inspect(connection).get_columns("tasks")
        }

    engine.dispose()
