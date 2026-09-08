import importlib
import json
from unittest.mock import patch

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_visibility_migration_preserves_materials_and_pending_baseline():
    migration = importlib.import_module(
        "app.storage.migrations.versions.1035_unify_agent_visibility"
    )
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        for table, column, hidden in (
            ("notes", "is_writing_visible", True),
            ("characters", "is_writing_visible", False),
            ("world_info_entries", "is_enabled", False),
            ("revision_note_snapshots", "is_writing_visible", True),
            ("revision_character_snapshots", "is_writing_visible", False),
            ("revision_world_entry_snapshots", "is_enabled", False),
        ):
            extra = ", is_hidden INTEGER" if hidden else ""
            connection.execute(
                text(
                    f'CREATE TABLE {table} (id TEXT PRIMARY KEY, content TEXT, "order" INTEGER, is_locked INTEGER, folder_id TEXT, {column} INTEGER{extra})'
                )
            )
            for index, (visible, is_hidden) in enumerate(((1, 0), (0, 0), (0, 1), (1, 1))):
                extra_value = f", {is_hidden}" if hidden else ""
                connection.execute(
                    text(
                        f"INSERT INTO {table} VALUES ('{index}', '正文原样', {index}, 1, 'folder', {visible}{extra_value})"
                    )
                )
        connection.execute(
            text("CREATE TABLE project_import_profiles (project_id TEXT, mapping_yaml TEXT)")
        )
        connection.execute(text("CREATE TABLE project_import_bindings (id TEXT, target_kind TEXT)"))
        connection.execute(
            text(
                'CREATE TABLE pending_project_changes (id TEXT, target_type TEXT, base_hash TEXT, "before" TEXT, "after" TEXT)'
            )
        )
        before = {
            "kind": "note",
            "title": "标题",
            "body": "正文",
            "writing_visible": False,
            "is_hidden": True,
        }
        connection.execute(
            text("INSERT INTO pending_project_changes VALUES (:id, :kind, :hash, :before, :after)"),
            {
                "id": "pending",
                "kind": "note",
                "hash": migration._hash(before),
                "before": json.dumps(before),
                "after": json.dumps({"writing_visible": True, "body": "修改后"}),
            },
        )
        with patch.object(migration, "op", Operations(MigrationContext.configure(connection))):
            migration.upgrade()
        for table in (
            "notes",
            "characters",
            "world_info_entries",
            "revision_note_snapshots",
            "revision_character_snapshots",
            "revision_world_entry_snapshots",
        ):
            columns = {col["name"] for col in inspect(connection).get_columns(table)}
            assert not columns & {"is_writing_visible", "is_hidden", "is_enabled"}
            rows = connection.execute(
                text(
                    f'SELECT content, "order", is_locked, folder_id, agent_visibility FROM {table} ORDER BY id'
                )
            ).all()
            expected = (
                ["all", "global", "none", "none"]
                if "note" in table
                else ["all", "global", "global", "all"]
            )
            assert rows == [
                ("正文原样", index, 1, "folder", value) for index, value in enumerate(expected)
            ]
        row = connection.execute(
            text('SELECT base_hash, "before", "after" FROM pending_project_changes')
        ).one()
        assert json.loads(row.before)["agent_visibility"] == "none"
        assert row.base_hash == migration._hash(json.loads(row.before))
        assert json.loads(row.after) == {"agent_visibility": "none", "body": "修改后"}
    engine.dispose()
