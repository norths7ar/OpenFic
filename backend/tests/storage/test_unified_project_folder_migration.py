import importlib
from unittest.mock import patch

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_unified_folders_preserve_ids_contents_order_visibility_and_references():
    migration = importlib.import_module(
        "app.storage.migrations.versions.1034_unify_project_folders"
    )
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        statements = [
            """CREATE TABLE project_folders (id TEXT PRIMARY KEY, project_id TEXT, scope TEXT, title TEXT, "order" INTEGER, created_at TEXT, updated_at TEXT, CONSTRAINT uq_project_folders_project_scope_title UNIQUE(project_id, scope, title))""",
            """CREATE TABLE volumes (id TEXT PRIMARY KEY, project_id TEXT, title TEXT, description TEXT, "order" INTEGER, chapter_count INTEGER, created_at TEXT, updated_at TEXT)""",
            """CREATE TABLE note_categories (id TEXT PRIMARY KEY, project_id TEXT, parent_id TEXT, title TEXT, document_type TEXT, "order" INTEGER, created_at TEXT, updated_at TEXT)""",
            """CREATE TABLE chapters (id TEXT PRIMARY KEY, volume_id TEXT NOT NULL REFERENCES volumes(id), content TEXT, "order" INTEGER)""",
            """CREATE TABLE chapter_summaries (id TEXT PRIMARY KEY, volume_id TEXT REFERENCES volumes(id), content TEXT)""",
            """CREATE TABLE notes (id TEXT PRIMARY KEY, category_id TEXT REFERENCES note_categories(id), document_type TEXT, content TEXT, "order" INTEGER, is_hidden INTEGER, is_writing_visible INTEGER, is_locked INTEGER)""",
            """CREATE TABLE revision_note_snapshots (id TEXT PRIMARY KEY, note_id TEXT)""",
            """CREATE TABLE revision_note_category_snapshots (id TEXT PRIMARY KEY, category_id TEXT)""",
            """INSERT INTO project_folders VALUES ('f','p','world','同名',4,'created','updated')""",
            """INSERT INTO volumes VALUES ('v1','p','同名','描述',2,1,'created','updated'), ('v2','p','同名',NULL,7,0,'created','updated')""",
            """INSERT INTO note_categories VALUES ('n','p',NULL,'同名','note',3,'created','updated'), ('o','p',NULL,'同名','outline',8,'created','updated')""",
            """INSERT INTO chapters VALUES ('chapter','v1','章节正文',12)""",
            """INSERT INTO chapter_summaries VALUES ('summary','v1','摘要')""",
            """INSERT INTO notes VALUES ('note','n','note','笔记正文',9,0,1,1), ('outline','o','outline','提纲正文',5,1,0,0)""",
            """INSERT INTO revision_note_snapshots VALUES ('s','outline')""",
            """INSERT INTO revision_note_category_snapshots VALUES ('s','o')""",
        ]
        for statement in statements:
            connection.execute(text(statement))
        before = {
            table: connection.execute(text(f"SELECT * FROM {table} ORDER BY id")).all()
            for table in ("chapters", "chapter_summaries", "notes")
        }
        with patch.object(migration, "op", Operations(MigrationContext.configure(connection))):
            migration.upgrade()
        for table, records in before.items():
            assert connection.execute(text(f"SELECT * FROM {table} ORDER BY id")).all() == records
            assert (
                inspect(connection).get_foreign_keys(table)[0]["referred_table"]
                == "project_folders"
            )
        assert connection.execute(
            text('SELECT id, scope, "order", description FROM project_folders ORDER BY id')
        ).all() == [
            ("f", "world", 4, None),
            ("n", "note", 3, None),
            ("o", "outline", 8, None),
            ("v1", "writing", 2, "描述"),
            ("v2", "writing", 7, None),
        ]
        assert not {"volumes", "note_categories"} & set(inspect(connection).get_table_names())
        assert (
            connection.execute(
                text("SELECT document_type FROM revision_note_snapshots")
            ).scalar_one()
            == "outline"
        )
        assert (
            connection.execute(
                text("SELECT scope FROM revision_note_category_snapshots")
            ).scalar_one()
            == "outline"
        )
        assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
        connection.execute(text("INSERT INTO chapters VALUES ('root',NULL,'根目录',1)"))
    engine.dispose()
