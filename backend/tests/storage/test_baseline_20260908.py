from __future__ import annotations

import importlib
from unittest.mock import patch

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

migration = importlib.import_module("app.storage.migrations.versions.20260908_baseline")


def test_frozen_baseline_creates_current_snapshot_and_import_binding_schema() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        with patch.object(migration, "op", operations):
            migration.upgrade()

        inspector = inspect(connection)
        snapshot_columns = {
            column["name"]: column for column in inspector.get_columns("revision_chapter_snapshots")
        }
        assert snapshot_columns["volume_id"]["nullable"]
        assert "project_folders" not in {
            foreign_key["referred_table"]
            for foreign_key in inspector.get_foreign_keys("revision_chapter_snapshots")
        }
        assert "ix_revision_chapter_snapshots_volume_id" in {
            index["name"] for index in inspector.get_indexes("revision_chapter_snapshots")
        }
        binding_sql = connection.execute(
            text(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'table' AND name = 'project_import_bindings'"
            )
        ).scalar_one()
        assert "'chapter'" in binding_sql
        assert "openfic_maintenance_migrations" not in inspector.get_table_names()
