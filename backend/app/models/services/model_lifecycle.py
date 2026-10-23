"""Transactional reference cleanup shared by every model retirement entry point."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities.model import Model
from app.storage.repos import agent_definition_repo, retrieval_index_repo, setting_repo

SETTING_LABELS = {
    "default_model": "默认模型",
    "light_model": "轻量模型",
    "default_embedding_model": "默认 Embedding 模型",
    "default_rerank_model": "默认 Rerank 模型",
}


async def model_uses(session: AsyncSession, model_id: str) -> list[str]:
    uses = []
    for key, label in SETTING_LABELS.items():
        setting = await setting_repo.get_by_key(session, key)
        if setting and setting.value == model_id:
            uses.append(label)
    uses.extend(
        f"Agent：{definition.display_name}"
        for definition in await agent_definition_repo.list_all(session)
        if definition.model_id == model_id
    )
    if await retrieval_index_repo.exists_by_embedding_model_ref_id(session, model_id):
        uses.append("章节检索索引")
    return uses


async def release_model_references(session: AsyncSession, model: Model) -> list[str]:
    """Never rewrite checkpoints/history or mutate an in-flight runtime config."""
    if await retrieval_index_repo.exists_by_embedding_model_ref_id(session, model.id):
        raise ValueError("Embedding model is bound to retrieval indexes; cannot retire it")
    uses = await model_uses(session, model.id)
    for key in SETTING_LABELS:
        setting = await setting_repo.get_by_key(session, key)
        if setting and setting.value == model.id:
            await setting_repo.upsert(session, key, "")
    for definition in await agent_definition_repo.list_all(session):
        if definition.model_id == model.id:
            definition.model_id = None
            session.add(definition)
    await session.flush()
    return uses
