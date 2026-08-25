"""Agent tool for proposing project-material changes for later review."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.agent_runtime.tools.base import AgentTool
from app.agent_runtime.tools.errors import ToolExecutionError
from app.agent_runtime.tools.registry import ToolRegistry
from app.storage.database import create_session
from app.storage.services import pending_project_change_service

PendingTargetType = Literal["note", "note_category", "character", "world_entry"]
PendingOperation = Literal["create", "update", "delete"]


class ProposeProjectChangeInput(BaseModel):
    target_type: PendingTargetType = Field(description="正式资料类型")
    target_id: str | None = Field(
        default=None,
        description="要更新或删除的资料 ID；创建时不填写",
    )
    operation: PendingOperation = Field(description="候审操作")
    after: dict[str, Any] | None = Field(
        default=None,
        description="创建或更新后的资料内容；删除时必须为空",
    )

    @model_validator(mode="after")
    def validate_operation_shape(self) -> ProposeProjectChangeInput:
        if self.operation == "create":
            if self.target_id is not None:
                raise ValueError("create 不能指定 target_id")
            if self.after is None:
                raise ValueError("create 必须提供 after")
        elif self.operation == "update":
            if not self.target_id:
                raise ValueError("update 必须指定 target_id")
            if self.after is None:
                raise ValueError("update 必须提供 after")
        else:
            if not self.target_id:
                raise ValueError("delete 必须指定 target_id")
            if self.after is not None:
                raise ValueError("delete 的 after 必须为空")
        return self


def _source_message_id(tool: AgentTool) -> str | None:
    state_value = tool._state.get("current_message_id")
    if isinstance(state_value, str) and state_value:
        return state_value
    config = tool.config
    configurable = config.get("configurable") if isinstance(config, dict) else None
    runtime_context = (
        configurable.get("runtime_context") if isinstance(configurable, dict) else None
    )
    if isinstance(runtime_context, Mapping):
        value = runtime_context.get("current_message_id")
        if isinstance(value, str) and value:
            return value
    return None


@ToolRegistry.register
class ProposeProjectChangeTool(AgentTool):
    name: str = "propose_project_change"
    description: str = (
        "为当前项目创建一条待用户审核的资料变更提议；只写入候审队列，"
        "不会直接修改正式资料。"
    )
    access_level: str = "write"
    args_schema: type[BaseModel] = ProposeProjectChangeInput

    async def _execute(
        self,
        target_type: PendingTargetType,
        target_id: str | None = None,
        operation: PendingOperation = "create",
        after: dict[str, Any] | None = None,
    ) -> str:
        project_id = self._state.get("project_id")
        if not isinstance(project_id, str) or not project_id:
            raise ToolExecutionError("缺少当前项目，无法创建候审变更")

        model_config = self._state.get("model_config")
        model_id: str | None = None
        if isinstance(model_config, Mapping):
            configured_model_id = model_config.get("model_id")
            if not isinstance(configured_model_id, str) or not configured_model_id:
                configured_model_id = model_config.get("model_record_id")
            if isinstance(configured_model_id, str) and configured_model_id:
                model_id = configured_model_id

        session = await create_session()
        try:
            change = await pending_project_change_service.create_pending_change(
                session,
                project_id=project_id,
                target_type=target_type,
                target_id=target_id,
                operation=operation,
                after=after,
                source_task_id=self._state.get("task_id"),
                source_message_id=_source_message_id(self),
                model_id=model_id,
            )
            await session.commit()
            return json.dumps(
                {
                    "success": True,
                    "pending_change_id": change.id,
                    "pending_change": {
                        "id": change.id,
                        "project_id": change.project_id,
                        "target_type": change.target_type,
                        "target_id": change.target_id,
                        "operation": change.operation,
                        "status": change.status,
                        "base_hash": change.base_hash,
                        "before": change.before,
                        "after": change.after,
                        "source_task_id": change.source_task_id,
                        "source_message_id": change.source_message_id,
                        "model_id": change.model_id,
                    },
                    "message": "已创建候审变更；正式资料尚未修改，请审核后采用。",
                },
                ensure_ascii=False,
            )
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
