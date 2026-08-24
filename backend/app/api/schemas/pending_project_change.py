"""待审项目变更 API schema。"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

PendingProjectChangeOperation = Literal["create", "update", "delete"]
PendingProjectChangeStatus = Literal["pending", "rejected"]


class PendingProjectChangeCreate(BaseModel):
    """创建待审项目变更请求。"""

    target_type: str = Field(min_length=1, max_length=100)
    target_id: str | None = Field(default=None, max_length=200)
    operation: PendingProjectChangeOperation
    base_hash: str | None = Field(default=None, max_length=128)
    before: Any = None
    after: Any = None
    source_task_id: str | None = Field(default=None, max_length=128)
    source_message_id: str | None = Field(default=None, max_length=128)
    model_id: str | None = Field(default=None, max_length=200)


class PendingProjectChangeResponse(BaseModel):
    """待审项目变更响应。"""

    id: str
    project_id: str
    target_type: str
    target_id: str | None
    operation: PendingProjectChangeOperation
    base_hash: str | None
    before: Any
    after: Any
    source_task_id: str | None
    source_message_id: str | None
    model_id: str | None
    status: PendingProjectChangeStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
