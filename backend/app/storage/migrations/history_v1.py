"""Frozen SQLite document recovery trigger definitions for migration 20260909."""

TABLES = {
    "chapters": (
        "chapter",
        "title",
        "content",
        "project_id",
        "id project_id volume_id title content word_count order created_at updated_at",
    ),
    "notes": (
        None,
        "title",
        "content",
        "project_id",
        "id project_id category_id title document_type order content is_locked agent_visibility created_at updated_at",
    ),
    "characters": (
        "character",
        "name",
        "description",
        "project_id",
        "id project_id folder_id name description image_path is_favorited order agent_visibility created_at updated_at",
    ),
    "world_info_entries": (
        "world_entry",
        "name",
        "content",
        None,
        "id world_info_id folder_id uid name section order content token_count agent_visibility created_at updated_at",
    ),
}


def install(connection):
    for table, (kind, title, body, project, columns) in TABLES.items():
        kind_sql = f"'{kind}'" if kind else "OLD.document_type"
        project_sql = (
            "OLD.project_id"
            if project
            else "(SELECT project_id FROM world_info WHERE id=OLD.world_info_id)"
        )
        payload = "json_object(" + ",".join(f"'{c}',OLD.\"{c}\"" for c in columns.split()) + ")"
        identity = f"project_id={project_sql} AND document_id=OLD.id AND kind={kind_sql}"
        connection.exec_driver_sql(f"""
            CREATE TRIGGER IF NOT EXISTS history_{table}_update BEFORE UPDATE ON {table}
            WHEN OLD.{title} IS NOT NEW.{title} OR OLD.{body} IS NOT NEW.{body}
            BEGIN
              INSERT INTO document_history(id,project_id,document_id,kind,title,content,source,created_at)
              SELECT lower(hex(randomblob(16))),{project_sql},OLD.id,{kind_sql},OLD.{title},OLD.{body},
                     openfic_history_source(),strftime('%Y-%m-%d %H:%M:%f','now')
              WHERE {project_sql} IS NOT NULL AND (
                openfic_history_source() != 'manual' OR NOT EXISTS (
                  SELECT 1 FROM document_history WHERE {identity}
                  AND id=(SELECT id FROM document_history WHERE {identity} ORDER BY created_at DESC,rowid DESC LIMIT 1)
                  AND source='manual' AND julianday(created_at)>julianday('now','-5 minutes')
                )
              );
              DELETE FROM document_history WHERE {identity} AND id NOT IN (
                SELECT id FROM document_history WHERE {identity} ORDER BY created_at DESC,rowid DESC LIMIT 100
              );
            END
        """)
        connection.exec_driver_sql(f"""
            CREATE TRIGGER IF NOT EXISTS history_{table}_delete BEFORE DELETE ON {table}
            WHEN {project_sql} IS NOT NULL
            BEGIN
              INSERT INTO document_trash(id,project_id,document_id,kind,title,content,payload,deleted_at)
              VALUES(lower(hex(randomblob(16))),{project_sql},OLD.id,{kind_sql},OLD.{title},OLD.{body},
                     {payload},strftime('%Y-%m-%d %H:%M:%f','now'));
            END
        """)
        connection.exec_driver_sql(f"""
            CREATE TRIGGER IF NOT EXISTS history_{table}_insert AFTER INSERT ON {table}
            BEGIN
              DELETE FROM document_trash WHERE document_id=NEW.id AND kind={kind_sql.replace("OLD.", "NEW.")};
            END
        """)
    connection.exec_driver_sql("""
        CREATE TRIGGER IF NOT EXISTS history_project_delete AFTER DELETE ON projects
        BEGIN
          DELETE FROM document_history WHERE project_id=OLD.id;
          DELETE FROM document_trash WHERE project_id=OLD.id;
        END
    """)


def uninstall(connection):
    for table in TABLES:
        for operation in ("update", "delete", "insert"):
            connection.exec_driver_sql(f"DROP TRIGGER IF EXISTS history_{table}_{operation}")
    connection.exec_driver_sql("DROP TRIGGER IF EXISTS history_project_delete")
