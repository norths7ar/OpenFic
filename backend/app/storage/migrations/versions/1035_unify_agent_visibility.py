"""Replace material visibility Booleans once; runtime has one policy field."""

import hashlib
import json

import sqlalchemy as sa
import yaml
from alembic import op

revision = "1035"
down_revision = "1034"
branch_labels = None
depends_on = None


def _hash(value: dict) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _convert_payload(value):
    if not isinstance(value, dict):
        return value
    result = dict(value)
    hidden = result.pop("is_hidden", False)
    visible = result.pop(
        "writing_visible", result.pop("is_writing_visible", result.pop("is_enabled", True))
    )
    result["agent_visibility"] = "none" if hidden else "all" if visible else "global"
    return result


def rebase_visibility_profiles(bind):
    """Rebase only proven clean baselines; leave divergent hashes untouched."""
    counts = {"profiles": 0, "rebased": 0, "divergent": 0}
    for profile in bind.execute(
        sa.text("SELECT project_id, mapping_yaml FROM project_import_profiles")
    ).mappings():
        config = yaml.safe_load(profile["mapping_yaml"])
        changed = False
        for rule in config["rules"]:
            if "writing_visible" in rule:
                rule["agent_visibility"] = "all" if rule.pop("writing_visible") else "global"
                changed = True
            if "disabled_title_suffix" in rule:
                rule.pop("disabled_title_suffix")
                changed = True
        if changed:
            bind.execute(
                sa.text(
                    "UPDATE project_import_profiles SET mapping_yaml=:mapping WHERE project_id=:id"
                ),
                {
                    "mapping": yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
                    "id": profile["project_id"],
                },
            )
            counts["profiles"] += 1
    for binding in bind.execute(
        sa.text(
            "SELECT * FROM project_import_bindings WHERE target_kind IN ('world_entry', 'character', 'note')"
        )
    ).mappings():
        kind = binding["target_kind"]
        table = {"world_entry": "world_info_entries", "character": "characters", "note": "notes"}[
            kind
        ]
        row = (
            bind.execute(
                sa.text(f"SELECT * FROM {table} WHERE id=:id"), {"id": binding["target_id"]}
            )
            .mappings()
            .first()
        )
        if row is None:
            continue
        fields = {
            "kind": kind,
            "id": row["id"],
            "project_id": binding["project_id"],
            "order": row["order"],
        }
        if kind == "world_entry":
            project_id = bind.execute(
                sa.text("SELECT project_id FROM world_info WHERE id=:id"),
                {"id": row["world_info_id"]},
            ).scalar_one()
            if project_id != binding["project_id"]:
                raise RuntimeError("Cross-project source binding")
            fields.update(
                world_info_id=row["world_info_id"],
                uid=row["uid"],
                section=row["section"],
                writing_visible=bool(row["is_enabled"]),
                folder_id=row["folder_id"],
            )
            title, body = row["name"], row["content"]
        else:
            if row["project_id"] != binding["project_id"]:
                raise RuntimeError("Cross-project source binding")
            fields["writing_visible"] = bool(row["is_writing_visible"])
            if kind == "character":
                fields.update(is_favorited=bool(row["is_favorited"]), folder_id=row["folder_id"])
                title, body = row["name"], row["description"]
            else:
                fields.update(
                    category_id=row["category_id"],
                    document_type=row["document_type"],
                    is_locked=bool(row["is_locked"]),
                    is_hidden=bool(row["is_hidden"]),
                )
                title, body = row["title"], row["content"]
        # Older native imports may omit optional folder_id from their baseline.
        candidates = [fields]
        if "folder_id" in fields:
            candidates.append({key: value for key, value in fields.items() if key != "folder_id"})
        baseline = next(
            (
                candidate
                for candidate in candidates
                if _hash({**candidate, "title": title, "body": body})
                == binding["last_applied_hash"]
            ),
            None,
        )
        if baseline is None:
            counts["divergent"] += 1
            continue
        updated = dict(baseline)
        visible = updated.pop("writing_visible")
        hidden = updated.pop("is_hidden", False)
        updated["agent_visibility"] = "none" if hidden else "all" if visible else "global"
        bind.execute(
            sa.text("UPDATE project_import_bindings SET last_applied_hash=:hash WHERE id=:id"),
            {"hash": _hash({**updated, "title": title, "body": body}), "id": binding["id"]},
        )
        counts["rebased"] += 1
    return counts


def upgrade() -> None:
    bind = op.get_bind()
    rebase_visibility_profiles(bind)
    for table, visible_column, hidden_column in (
        ("notes", "is_writing_visible", "is_hidden"),
        ("characters", "is_writing_visible", None),
        ("world_info_entries", "is_enabled", None),
        ("revision_note_snapshots", "is_writing_visible", "is_hidden"),
        ("revision_character_snapshots", "is_writing_visible", None),
        ("revision_world_entry_snapshots", "is_enabled", None),
    ):
        snapshot = table.startswith("revision_")
        op.add_column(
            table,
            sa.Column(
                "agent_visibility",
                sa.String(),
                nullable=snapshot,
                server_default=None if snapshot else "all",
            ),
        )
        hidden_case = f"WHEN {hidden_column} = 1 THEN 'none' " if hidden_column else ""
        bind.execute(
            sa.text(
                f"UPDATE {table} SET agent_visibility = CASE {hidden_case}WHEN {visible_column} = 0 THEN 'global' ELSE 'all' END"
            )
        )
        old_columns = {visible_column} | ({hidden_column} if hidden_column else set())
        indexes = sa.inspect(bind).get_indexes(table)
        with op.batch_alter_table(table) as batch:
            for index in indexes:
                if set(index["column_names"]) & old_columns:
                    batch.drop_index(index["name"])
            for column in old_columns:
                batch.drop_column(column)
            if not snapshot:
                batch.create_index(f"ix_{table}_agent_visibility", ["agent_visibility"])

    for row in (
        bind.execute(
            sa.text(
                'SELECT id, target_type, base_hash, "before", "after" FROM pending_project_changes'
            )
        )
        .mappings()
        .all()
    ):
        if row["target_type"] == "note_category":
            continue
        before = json.loads(row["before"]) if row["before"] else None
        after = json.loads(row["after"]) if row["after"] else None
        converted_before, converted_after = _convert_payload(before), _convert_payload(after)
        # Old pending updates could change writing visibility, but could not
        # clear the independent hidden flag on an existing note.
        if (
            isinstance(before, dict)
            and before.get("is_hidden")
            and isinstance(after, dict)
            and "is_hidden" not in after
        ):
            converted_after["agent_visibility"] = "none"
        base_hash = row["base_hash"]
        if isinstance(before, dict) and base_hash == _hash(before):
            base_hash = _hash(converted_before)
        bind.execute(
            sa.text(
                'UPDATE pending_project_changes SET "before"=:before, "after"=:after, base_hash=:base_hash WHERE id=:id'
            ),
            {
                "id": row["id"],
                "before": json.dumps(converted_before, ensure_ascii=False),
                "after": json.dumps(converted_after, ensure_ascii=False),
                "base_hash": base_hash,
            },
        )


def downgrade() -> None:
    raise RuntimeError(
        "Visibility states cannot be represented losslessly as old Booleans; restore the pre-upgrade backup."
    )
