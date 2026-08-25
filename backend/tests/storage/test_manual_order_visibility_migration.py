import importlib
from unittest.mock import patch

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

migration = importlib.import_module(
    "app.storage.migrations.versions.1021_add_manual_order_and_writing_visibility"
)


def _create_previous_schema(connection) -> None:
    connection.execute(
        text(
            "CREATE TABLE characters ("
            "id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL, "
            "is_favorited BOOLEAN NOT NULL, updated_at DATETIME NOT NULL)"
        )
    )
    connection.execute(
        text(
            "CREATE TABLE notes ("
            "id TEXT PRIMARY KEY, project_id TEXT NOT NULL, category_id TEXT, "
            "title TEXT NOT NULL)"
        )
    )
    connection.execute(
        text(
            "CREATE TABLE note_categories ("
            "id TEXT PRIMARY KEY, project_id TEXT NOT NULL, parent_id TEXT, "
            "title TEXT NOT NULL)"
        )
    )
    connection.execute(
        text("CREATE TABLE revision_character_snapshots (id TEXT PRIMARY KEY)")
    )
    connection.execute(
        text("CREATE TABLE revision_note_snapshots (id TEXT PRIMARY KEY)")
    )
    connection.execute(
        text("CREATE TABLE revision_note_category_snapshots (id TEXT PRIMARY KEY)")
    )


def test_upgrade_backfills_existing_display_order_and_visibility() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        _create_previous_schema(connection)
        connection.execute(
            text(
                "INSERT INTO characters "
                "(id, project_id, name, is_favorited, updated_at) VALUES "
                "('normal', 'project-1', '普通', 0, '2026-08-25 12:00:00'), "
                "('favorite-old', 'project-1', '收藏旧', 1, '2026-08-24 12:00:00'), "
                "('favorite-new', 'project-1', '收藏新', 1, '2026-08-25 12:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO notes (id, project_id, category_id, title) VALUES "
                "('root-b', 'project-1', NULL, '乙'), "
                "('root-a', 'project-1', NULL, '甲'), "
                "('child', 'project-1', 'category-1', '子项')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO note_categories (id, project_id, parent_id, title) VALUES "
                "('root-b', 'project-1', NULL, '乙'), "
                "('root-a', 'project-1', NULL, '甲'), "
                "('child', 'project-1', 'root-a', '子类')"
            )
        )

        operations = Operations(MigrationContext.configure(connection))
        with patch.object(migration, "op", operations):
            migration.upgrade()

        characters = (
            connection.execute(
                text(
                    'SELECT id, "order", is_writing_visible FROM characters '
                    'ORDER BY "order"'
                )
            )
            .mappings()
            .all()
        )
        assert [row["id"] for row in characters] == [
            "favorite-new",
            "favorite-old",
            "normal",
        ]
        assert [row["order"] for row in characters] == [1, 2, 3]
        assert all(row["is_writing_visible"] for row in characters)

        root_notes = (
            connection.execute(
                text(
                    'SELECT id, "order", is_writing_visible FROM notes '
                    'WHERE category_id IS NULL ORDER BY "order"'
                )
            )
            .mappings()
            .all()
        )
        assert [row["id"] for row in root_notes] == ["root-b", "root-a"]
        assert [row["order"] for row in root_notes] == [1, 2]
        assert all(row["is_writing_visible"] for row in root_notes)

        root_categories = (
            connection.execute(
                text(
                    'SELECT id, "order" FROM note_categories '
                    'WHERE parent_id IS NULL ORDER BY "order"'
                )
            )
            .mappings()
            .all()
        )
        assert [row["id"] for row in root_categories] == ["root-b", "root-a"]
        assert [row["order"] for row in root_categories] == [1, 2]

        indexes = {
            index["name"]
            for table_name in ("characters", "notes", "note_categories")
            for index in inspect(connection).get_indexes(table_name)
        }
        assert {
            "ix_characters_order",
            "ix_characters_is_writing_visible",
            "ix_notes_order",
            "ix_notes_is_writing_visible",
            "ix_note_categories_order",
        } <= indexes

        with patch.object(migration, "op", operations):
            migration.downgrade()

        assert "order" not in {
            column["name"] for column in inspect(connection).get_columns("characters")
        }
        assert "is_writing_visible" not in {
            column["name"] for column in inspect(connection).get_columns("notes")
        }

    engine.dispose()
