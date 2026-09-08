"""Exercise real SQLModel construction, mutation, SQL binds and hydration."""

import pytest
from sqlalchemy import create_engine, inspect, text, update
from sqlalchemy.exc import StatementError
from sqlmodel import Session, SQLModel, select

from app.core.agent_visibility import AgentVisibility
from app.storage.models.character import Character
from app.storage.models.note import Note
from app.storage.models.revision_character_snapshot import RevisionCharacterSnapshot
from app.storage.models.revision_note_snapshot import RevisionNoteSnapshot
from app.storage.models.revision_world_entry_snapshot import RevisionWorldEntrySnapshot
from app.storage.models.world_info_entry import WorldInfoEntry

MATERIALS = (Note, Character, WorldInfoEntry)
SNAPSHOTS = (RevisionNoteSnapshot, RevisionCharacterSnapshot, RevisionWorldEntrySnapshot)


@pytest.mark.parametrize("model", (*MATERIALS, *SNAPSHOTS))
def test_model_constructs_and_assigns_enum_and_rejects_invalid_without_mutation(model):
    # Other fields are intentionally omitted: this test checks the actual table
    # constructor, not a separate Pydantic request model.
    record = model(agent_visibility="global")
    assert record.agent_visibility is AgentVisibility.GLOBAL
    record.agent_visibility = "all"
    assert record.agent_visibility is AgentVisibility.ALL
    for invalid in ("typo", "ALL", "", True, 1):
        with pytest.raises(ValueError):
            model(agent_visibility=invalid)
        with pytest.raises(ValueError):
            record.agent_visibility = invalid
        assert record.agent_visibility is AgentVisibility.ALL


@pytest.mark.parametrize("model", MATERIALS)
def test_material_visibility_cannot_be_null(model):
    record = model()
    assert record.agent_visibility is AgentVisibility.ALL
    with pytest.raises(ValueError):
        record.agent_visibility = None
    assert record.agent_visibility is AgentVisibility.ALL
    with pytest.raises(ValueError):
        model(agent_visibility=None)


@pytest.mark.parametrize("model", SNAPSHOTS)
def test_absent_material_snapshot_can_have_null_visibility(model):
    record = model()
    assert record.agent_visibility is None
    record.agent_visibility = AgentVisibility.NONE
    record.agent_visibility = None
    assert record.agent_visibility is None


def test_sql_roundtrip_uses_values_and_rejects_invalid_bind_and_load():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        note = Note(project_id="project", title="note", agent_visibility=AgentVisibility.GLOBAL)
        session.add(note)
        session.commit()
        note_id = note.id
        assert session.execute(text("SELECT agent_visibility FROM notes")).scalar_one() == "global"
        session.expunge_all()
        loaded = session.exec(select(Note)).one()
        assert loaded.agent_visibility is AgentVisibility.GLOBAL

        with pytest.raises(ValueError):
            loaded.agent_visibility = "bad"
        assert loaded.agent_visibility is AgentVisibility.GLOBAL
        assert not inspect(loaded).attrs.agent_visibility.history.has_changes()

        with pytest.raises(StatementError):
            session.execute(update(Note).values(agent_visibility="bad"))
        session.rollback()
        session.execute(
            text("UPDATE notes SET agent_visibility='unknown' WHERE id=:id"), {"id": note_id}
        )
        session.commit()
        session.expunge_all()
        with pytest.raises(LookupError):
            session.exec(select(Note)).one()
    engine.dispose()
