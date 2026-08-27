"""Agent tool for proposing project-material changes for later review."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent_runtime.tools.base import AgentTool
from app.agent_runtime.tools.errors import ToolExecutionError
from app.agent_runtime.tools.registry import ToolRegistry
from app.storage.database import create_session
from app.storage.services import pending_project_change_service

PendingTargetType = Literal["note", "note_category", "character", "world_entry"]
PendingOperation = Literal["create", "update", "delete"]


class _ProposedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProposedNotePayload(_ProposedPayload):
    kind: Literal["note"] = Field(description="资料类型，固定为 note")
    title: str = Field(description="笔记或提纲标题", min_length=1, max_length=200)
    body: str = Field(default="", description="笔记或提纲正文")
    category_id: str | None = Field(default=None, description="所属分类 ID")
    writing_visible: bool = Field(default=True, description="写作 Agent 是否可见")
    document_type: Literal["note", "outline"] = Field(
        default="note", description="文档类型：普通笔记或提纲"
    )


class ProposedNoteCategoryPayload(_ProposedPayload):
    kind: Literal["note_category"] = Field(
        description="资料类型，固定为 note_category"
    )
    title: str = Field(description="分类名称", min_length=1, max_length=200)
    parent_id: None = Field(default=None, description="当前只允许创建顶级分类")
    document_type: Literal["note", "outline"] = Field(
        default="note", description="分类所包含的文档类型"
    )


class ProposedCharacterPayload(_ProposedPayload):
    kind: Literal["character"] = Field(description="资料类型，固定为 character")
    title: str = Field(description="角色名称", min_length=1, max_length=200)
    body: str = Field(default="", description="角色设定正文")
    writing_visible: bool = Field(default=True, description="写作 Agent 是否可见")


class ProposedWorldEntryPayload(_ProposedPayload):
    kind: Literal["world_entry"] = Field(description="资料类型，固定为 world_entry")
    title: str = Field(description="背景设定条目名称", min_length=1, max_length=200)
    body: str = Field(default="", description="背景设定正文")
    section: str = Field(default="", description="背景设定分区", max_length=500)
    writing_visible: bool = Field(default=True, description="写作 Agent 是否可见")


ProposedPayload = Annotated[
    ProposedNotePayload
    | ProposedNoteCategoryPayload
    | ProposedCharacterPayload
    | ProposedWorldEntryPayload,
    Field(discriminator="kind"),
]


class ProposeProjectChangeInput(BaseModel):
    target_type: PendingTargetType = Field(description="正式资料类型")
    target_id: str | None = Field(
        default=None,
        description="要更新或删除的资料 ID；创建时不填写",
    )
    operation: PendingOperation = Field(description="候审操作")
    after: ProposedPayload | None = Field(
        default=None,
        description=(
            "创建或更新后的资料内容；kind 必须与 target_type 一致，删除时必须为空"
        ),
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
        if self.after is not None and self.after.kind != self.target_type:
            raise ValueError("after.kind 必须与 target_type 一致")
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
        after: ProposedPayload | dict[str, Any] | None = None,
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

        serialized_after = (
            after.model_dump(mode="json") if isinstance(after, BaseModel) else after
        )

        session = await create_session()
        try:
            change = await pending_project_change_service.create_pending_change(
                session,
                project_id=project_id,
                target_type=target_type,
                target_id=target_id,
                operation=operation,
                after=serialized_after,
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
