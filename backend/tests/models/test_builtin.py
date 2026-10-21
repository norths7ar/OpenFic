"""
Builtin models tests - 内置 fastembed 模型的 seeding 与保护逻辑。
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.builtin import (
    BUILTIN_PROVIDER_ID,
    seed_builtin_models,
)
from app.models.entities.model import Model


@pytest.mark.asyncio
async def test_seed_builtin_models_is_idempotent(session: AsyncSession):
    await seed_builtin_models(session)
    await seed_builtin_models(session)

    result = await session.execute(
        select(Model).where(col(Model.provider_id) == BUILTIN_PROVIDER_ID)
    )
    models = list(result.scalars().all())
    assert len(models) == 2
