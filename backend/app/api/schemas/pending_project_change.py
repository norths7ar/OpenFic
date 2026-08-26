"""待审项目变更 API schema。"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

PendingProjectChangeOperation = Literal["create", "update", "delete"]
PendingProjectChangeStatus = Literal["pending", "applying", "rejected", "applied"]
PendingProjectChangeTargetType = Literal[
    "note",
    "note_category",
    "character",
    "world_entry",
]


class PendingProjectChangeCreate(BaseModel):
    """创建待审项目变更请求。"""

    target_type: PendingProjectChangeTargetType
    target_id: str | None = Field(default=None, max_length=200)
    operation: PendingProjectChangeOperation
    after: Any = None
    source_task_id: str | None = Field(default=None, max_length=128)
    source_message_id: str | None = Field(default=None, max_length=128)
    model_id: str | None = Field(default=None, max_length=200)

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_operation_shape(self) -> "PendingProjectChangeCreate":
        if self.operation == "create":
            if self.target_id is not None:
                raise ValueError("create 不能指定 target_id")
            if not isinstance(self.after, dict):
                raise ValueError("create 的 after 必须是对象")
        elif self.operation == "update":
            if not self.target_id:
                raise ValueError("update 必须指定 target_id")
            if not isinstance(self.after, dict):
                raise ValueError("update 的 after 必须是对象")
        else:
            if not self.target_id:
                raise ValueError("delete 必须指定 target_id")
            if self.after is not None:
                raise ValueError("delete 的 after 必须为空")
        return self


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
    is_applicable: bool = False
    applicability_reason: str | None = None
    applied_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
