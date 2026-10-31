"""AgentMemory API Schemas。"""

from datetime import datetime

from pydantic import ConfigDict, Field

from app.api.schemas.base import APIModel


class AgentMemoryCreate(APIModel):
    content: str = Field(default="", description="记忆内容")


class AgentMemoryUpdate(APIModel):
    content: str | None = Field(default=None, description="记忆内容")


class AgentMemoryReorder(APIModel):
    memory_ids: list[str] = Field(description="按新顺序排列的记忆 ID 列表")


class AgentMemoryResponse(APIModel):
    id: str
    content: str
    order_index: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentMemoryListResponse(APIModel):
    items: list[AgentMemoryResponse]
    total: int
    page: int
    page_size: int
