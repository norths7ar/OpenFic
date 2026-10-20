"""
Settings API 测试。
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import EncryptionService
from app.models.repos import model_provider_repo, model_repo
from app.storage.models.retrieval_chapter_index_state import RetrievalChapterIndexState
from app.storage.models.retrieval_index import RetrievalIndex
from app.storage.repos import setting_repo

EXPECTED_AGENT_TOOL_PERMISSIONS = [
    {"tool_name": "activate_skill", "mode": "allow"},
    {"tool_name": "ask_user", "mode": "allow"},
    {"tool_name": "create_character", "mode": "ask"},
    {"tool_name": "create_note_category", "mode": "ask"},
    {"tool_name": "create_volume", "mode": "ask"},
    {"tool_name": "create_world_entry", "mode": "ask"},
    {"tool_name": "delete_chapter", "mode": "ask"},
    {"tool_name": "delete_character", "mode": "ask"},
    {"tool_name": "delete_note", "mode": "ask"},
    {"tool_name": "delete_note_category", "mode": "ask"},
    {"tool_name": "delete_volume", "mode": "ask"},
    {"tool_name": "delete_world_entry", "mode": "ask"},
    {"tool_name": "dispatch_subagent", "mode": "allow"},
    {"tool_name": "edit_chapter", "mode": "ask"},
    {"tool_name": "edit_character", "mode": "ask"},
    {"tool_name": "edit_note", "mode": "ask"},
    {"tool_name": "edit_note_category", "mode": "ask"},
    {"tool_name": "edit_volume", "mode": "ask"},
    {"tool_name": "edit_world_entry", "mode": "ask"},
    {"tool_name": "list_chapters", "mode": "allow"},
    {"tool_name": "list_characters", "mode": "allow"},
    {"tool_name": "list_notes", "mode": "allow"},
    {"tool_name": "list_pending_project_changes", "mode": "allow"},
    {"tool_name": "list_volumes", "mode": "allow"},
    {"tool_name": "list_world_entries", "mode": "allow"},
    {"tool_name": "move_chapter_to_volume", "mode": "ask"},
    {"tool_name": "move_note", "mode": "ask"},
    {"tool_name": "notify_subagent", "mode": "allow"},
    {"tool_name": "propose_project_create", "mode": "allow"},
    {"tool_name": "propose_project_delete", "mode": "allow"},
    {"tool_name": "propose_project_update", "mode": "allow"},
    {"tool_name": "read_chapter", "mode": "allow"},
    {"tool_name": "read_chapter_summaries", "mode": "allow"},
    {"tool_name": "read_character", "mode": "allow"},
    {"tool_name": "read_note", "mode": "allow"},
    {"tool_name": "read_pending_project_change", "mode": "allow"},
    {"tool_name": "read_range_summaries", "mode": "allow"},
    {"tool_name": "read_world_entry", "mode": "allow"},
    {"tool_name": "recycle_subagent", "mode": "allow"},
    {"tool_name": "reference_skill", "mode": "allow"},
    {"tool_name": "revise_pending_project_change", "mode": "allow"},
    {"tool_name": "search_chapters", "mode": "allow"},
    {"tool_name": "update_index", "mode": "allow"},
    {"tool_name": "write_chapter", "mode": "ask"},
    {"tool_name": "write_note", "mode": "ask"},
    {"tool_name": "write_plan", "mode": "ask"},
]


async def _create_embedding_model(session: AsyncSession, model_id: str):
    from app.settings import settings

    encryption_service = EncryptionService(settings.encryption_key)
    provider = await model_provider_repo.create(
        session=session,
        name=f"Provider {model_id}",
        url="https://api.test.com",
        api_key_encrypted=encryption_service.encrypt("test-key"),
        provider_type="openai",
    )
    return await model_repo.create(
        session=session,
        name=f"Embedding {model_id}",
        provider_id=provider.id,
        model_id=model_id,
        task_type="embedding",
        dimensions=3,
    )


@pytest.mark.asyncio
async def test_changing_default_embedding_model_marks_retrieval_indexes_for_rebuild(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    old_model = await _create_embedding_model(session, "embed-old")
    new_model = await _create_embedding_model(session, "embed-new")
    retrieval_index = RetrievalIndex(
        index_key="chapters:project-1",
        table_name="chapters_project_1",
        status="ready",
        embedding_model_ref_id=old_model.id,
        embedding_model_id_snapshot=old_model.model_id,
        embedding_dimensions_snapshot=3,
    )
    chapter_state = RetrievalChapterIndexState(
        project_id="project-1",
        chapter_id="chapter-1",
        index_key="chapters:project-1",
        status="ready",
        source_hash="old-hash",
        embedding_model_ref_id=old_model.id,
        chunk_count=2,
    )
    session.add(retrieval_index)
    session.add(chapter_state)
    await setting_repo.upsert(session, "default_embedding_model", old_model.id)
    await session.commit()

    response = await client.patch(
        "/api/v1/settings",
        json={"default_embedding_model": new_model.id},
    )

    assert response.status_code == 200
    await session.refresh(retrieval_index)
    await session.refresh(chapter_state)
    assert response.json()["default_embedding_model"] == new_model.id
    assert retrieval_index.status == "needs_rebuild"
    assert chapter_state.status == "needs_rebuild"

    rows = (await session.execute(select(RetrievalChapterIndexState))).scalars().all()
    assert [row.status for row in rows] == ["needs_rebuild"]


@pytest.mark.asyncio
async def test_update_settings_agent_bypass_tool_approval(client: AsyncClient) -> None:
    """测试更新工具审批放行设置。"""
    response = await client.put(
        "/api/v1/settings",
        json={"agent_bypass_tool_approval": True},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["agent_bypass_tool_approval"] is True

    follow_up = await client.get("/api/v1/settings")
    assert follow_up.status_code == 200
    assert follow_up.json()["agent_bypass_tool_approval"] is True
