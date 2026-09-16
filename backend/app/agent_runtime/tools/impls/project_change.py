"""Agent tools for proposing project-material changes for later review."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent_runtime.context.knowledge_visibility import get_knowledge_scope
from app.agent_runtime.tools.base import AgentTool
from app.agent_runtime.tools.errors import ToolExecutionError
from app.agent_runtime.tools.registry import ToolRegistry
from app.core.agent_visibility import AgentVisibility, visible_in_scope
from app.storage.database import create_session
from app.storage.repos import pending_project_change_repo
from app.storage.services import (
    pending_project_change_apply_service,
    pending_project_change_service,
)

PendingTargetType = Literal["note", "note_category", "character", "world_entry"]
PendingOperation = Literal["create", "update", "delete"]


class _ProposalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProposeProjectCreateInput(_ProposalInput):
    target_type: PendingTargetType = Field(description="要创建的正式资料类型")
    title: str = Field(description="资料标题", min_length=1, max_length=200)
    body: str = Field(default="", description="资料正文；笔记分类不使用此字段")
    agent_visibility: AgentVisibility = Field(
        default=AgentVisibility.ALL,
        description="Agent 可见范围；笔记分类不使用此字段",
    )
    category_id: str | None = Field(
        default=None,
        description="新笔记所属分类 ID；仅 target_type=note 时使用",
    )
    document_type: Literal["note", "outline"] = Field(
        default="note",
        description="新笔记或分类的文档类型；仅 note/note_category 使用",
    )
    section: str = Field(
        default="",
        max_length=500,
        description="背景设定分区；仅 target_type=world_entry 时使用",
    )

    @model_validator(mode="after")
    def validate_target_fields(self) -> ProposeProjectCreateInput:
        # Callers may emit every schema default, including fields for other targets.
        # Explicit defaults have the same meaning as omitted defaults.
        supplied = {
            name
            for name in self.model_fields_set
            if getattr(self, name) != type(self).model_fields[name].default
        }
        if self.target_type != "note" and "category_id" in supplied:
            raise ValueError("category_id 只适用于新建笔记")
        if self.target_type not in {"note", "note_category"} and ("document_type" in supplied):
            raise ValueError("document_type 只适用于新建笔记或笔记分类")
        if self.target_type != "world_entry" and "section" in supplied:
            raise ValueError("section 只适用于新建背景设定")
        if self.target_type == "note_category" and ({"body", "agent_visibility"} & supplied):
            raise ValueError("笔记分类只需要标题和文档类型")
        return self


class ProposalTextEdit(_ProposalInput):
    old_content: str = Field(min_length=1, description="需要替换的原片段，必须在正文中唯一匹配")
    new_content: str = Field(description="替换后的片段；空字符串表示删除")


class ProjectChangePatch(_ProposalInput):
    title: str | None = Field(
        default=None,
        description="新标题；省略或 null 表示不修改",
        min_length=1,
        max_length=200,
    )
    body: str | None = Field(
        default=None, description="新正文；省略或 null 表示不修改，空字符串表示清空"
    )
    edits: list[ProposalTextEdit] | None = Field(
        default=None,
        min_length=1,
        description="按顺序执行的局部正文替换；与 body 互斥，小范围修改优先使用",
    )
    agent_visibility: AgentVisibility | None = Field(
        default=None,
        description="新的 Agent 可见范围；省略或 null 表示不修改",
    )
    section: str | None = Field(
        default=None,
        max_length=500,
        description="新的背景设定分区；仅 world_entry 可填写，省略或 null 表示不修改，空字符串表示清空",
    )


class ProposeProjectUpdateInput(ProjectChangePatch):
    target_type: PendingTargetType = Field(description="要更新的正式资料类型")
    target_id: str = Field(description="要更新的资料 ID", min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_patch(self) -> ProposeProjectUpdateInput:
        # Some tool callers fill unused string fields with an empty placeholder.
        # Only world entries have a section; do not forward that placeholder.
        if self.target_type != "world_entry" and self.section == "":
            self.section = None
        if self.body is not None and self.edits is not None:
            raise ValueError("body 和 edits 不能同时提供")
        patch_fields = {
            name
            for name in self.model_fields_set - {"target_type", "target_id"}
            if getattr(self, name) is not None
        }
        if not patch_fields:
            raise ValueError("update 至少要提供一个需要修改的字段")
        if self.target_type == "note_category" and patch_fields != {"title"}:
            raise ValueError("笔记分类只能修改标题")
        if self.target_type != "world_entry" and "section" in patch_fields:
            raise ValueError("section 只适用于背景设定")
        return self


class ProposeProjectDeleteInput(_ProposalInput):
    target_type: PendingTargetType = Field(description="要删除的正式资料类型")
    target_id: str = Field(description="要删除的资料 ID", min_length=1, max_length=200)


class ReadPendingProjectChangeInput(_ProposalInput):
    change_id: str = Field(description="待审提案 ID（不是正式资料 ID）", min_length=1)


class RevisePendingProjectChangeInput(ReadPendingProjectChangeInput):
    expected_updated_at: datetime = Field(description="读取提案返回的 updated_at，原样传回")
    patch: ProjectChangePatch = Field(
        description="修改当前待采用版本的字段：title、body 或 edits、agent_visibility、section；"
        "edits 使用 old_content/new_content，原片段来自待采用正文。分类只能修改 title。"
    )


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


def _model_id(tool: AgentTool) -> str | None:
    model_config = tool._state.get("model_config")
    if not isinstance(model_config, Mapping):
        return None
    configured_model_id = model_config.get("model_id")
    if not isinstance(configured_model_id, str) or not configured_model_id:
        configured_model_id = model_config.get("model_record_id")
    return configured_model_id if isinstance(configured_model_id, str) else None


def _create_after(
    target_type: PendingTargetType,
    *,
    title: str,
    body: str,
    agent_visibility: AgentVisibility,
    category_id: str | None,
    document_type: Literal["note", "outline"],
    section: str,
) -> dict[str, Any]:
    if target_type == "note":
        return {
            "title": title,
            "body": body,
            "category_id": category_id,
            "agent_visibility": agent_visibility,
            "document_type": document_type,
        }
    if target_type == "note_category":
        return {
            "title": title,
            "parent_id": None,
            "document_type": document_type,
        }
    if target_type == "character":
        return {
            "title": title,
            "body": body,
            "agent_visibility": agent_visibility,
        }
    return {
        "title": title,
        "body": body,
        "section": section,
        "agent_visibility": agent_visibility,
    }


async def _queue_pending_change(
    tool: AgentTool,
    *,
    target_type: PendingTargetType,
    target_id: str | None,
    operation: PendingOperation,
    after: dict[str, Any] | None,
) -> str:
    project_id = tool._state.get("project_id")
    if not isinstance(project_id, str) or not project_id:
        raise ToolExecutionError("缺少当前项目，无法创建候审变更")

    session = await create_session()
    try:
        existing = None
        if tool.tool_call_id:
            execution_id = pending_project_change_service.proposal_execution_id(
                project_id, tool._state.get("task_id"), _source_message_id(tool), tool.tool_call_id
            )
            existing = await pending_project_change_repo.get_by_id(
                session, project_id, execution_id
            )
        if existing is None and target_id and target_type != "note_category":
            _, snapshot = await pending_project_change_apply_service._resolve_snapshot(
                session, project_id, target_type, target_id
            )
            scope = get_knowledge_scope(tool._state)
            if not visible_in_scope(snapshot["agent_visibility"], scope):
                raise ToolExecutionError("资料不在当前知识范围内")
        change = existing or await pending_project_change_service.create_pending_change(
            session,
            project_id=project_id,
            target_type=target_type,
            target_id=target_id,
            operation=operation,
            after=after,
            source_task_id=tool._state.get("task_id"),
            source_message_id=_source_message_id(tool),
            model_id=_model_id(tool),
            tool_call_id=tool.tool_call_id,
        )
        await session.commit()
        before = change.before if isinstance(change.before, dict) else {}
        after_snapshot = change.after if isinstance(change.after, dict) else {}
        snapshot = after_snapshot or before
        changed_fields = [
            field
            for field in ("title", "body", "agent_visibility", "section")
            if before.get(field) != after_snapshot.get(field)
        ]
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
                    "title": snapshot.get("title", ""),
                    "document_type": snapshot.get("document_type"),
                    "changed_fields": changed_fields,
                    "source_task_id": change.source_task_id,
                    "source_message_id": change.source_message_id,
                    "model_id": change.model_id,
                },
                "message": "提案已提交。",
            },
            ensure_ascii=False,
        )
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@ToolRegistry.register
class ProposeProjectCreateTool(AgentTool):
    name: str = "propose_project_create"
    description: str = "为当前项目提议新建一项正式资料；只进入待审队列，不直接写入正式资料。"
    access_level: str = "write"
    args_schema: type[BaseModel] = ProposeProjectCreateInput

    async def _execute(
        self,
        target_type: PendingTargetType,
        title: str,
        body: str = "",
        agent_visibility: AgentVisibility = AgentVisibility.ALL,
        category_id: str | None = None,
        document_type: Literal["note", "outline"] = "note",
        section: str = "",
    ) -> str:
        return await _queue_pending_change(
            self,
            target_type=target_type,
            target_id=None,
            operation="create",
            after=_create_after(
                target_type,
                title=title,
                body=body,
                agent_visibility=agent_visibility,
                category_id=category_id,
                document_type=document_type,
                section=section,
            ),
        )


@ToolRegistry.register
class ProposeProjectUpdateTool(AgentTool):
    name: str = "propose_project_update"
    description: str = (
        "为当前项目提议修改一项正式资料；只填写真正要改的字段，"
        "小范围正文修改优先使用 edits，仅整体重写使用 body，两者互斥；"
        "分类、文档类型、顺序等未暴露字段由服务端原样保留。"
        "如需继续修改已有待审提案，使用 revise_pending_project_change。"
    )
    access_level: str = "write"
    args_schema: type[BaseModel] = ProposeProjectUpdateInput

    async def _execute(
        self,
        target_type: PendingTargetType,
        target_id: str,
        title: str | None = None,
        body: str | None = None,
        edits: list[ProposalTextEdit | dict[str, str]] | None = None,
        agent_visibility: AgentVisibility | None = None,
        section: str | None = None,
    ) -> str:
        patch = {
            key: value
            for key, value in {
                "title": title,
                "body": body,
                "edits": [
                    edit.model_dump() if isinstance(edit, ProposalTextEdit) else edit
                    for edit in edits
                ]
                if edits is not None
                else None,
                "agent_visibility": agent_visibility,
                "section": section,
            }.items()
            if value is not None
        }
        return await _queue_pending_change(
            self,
            target_type=target_type,
            target_id=target_id,
            operation="update",
            after=patch,
        )


@ToolRegistry.register
class ProposeProjectDeleteTool(AgentTool):
    name: str = "propose_project_delete"
    description: str = "为当前项目提议删除一项正式资料；只进入待审队列，不直接删除正式资料。"
    access_level: str = "write"
    args_schema: type[BaseModel] = ProposeProjectDeleteInput

    async def _execute(
        self,
        target_type: PendingTargetType,
        target_id: str,
    ) -> str:
        return await _queue_pending_change(
            self,
            target_type=target_type,
            target_id=target_id,
            operation="delete",
            after=None,
        )


def _pending_project_id(tool: AgentTool) -> str:
    project_id = tool._state.get("project_id")
    if not isinstance(project_id, str) or not project_id:
        raise ToolExecutionError("缺少当前项目")
    return project_id


async def _pending_visible(tool: AgentTool, session: Any, change: Any) -> bool:
    if change.target_type == "note_category":
        return True
    scope = get_knowledge_scope(tool._state)
    snapshots = [change.before, change.after]
    if change.target_id:
        from app.core.errors import NotFoundError

        try:
            _, current = await pending_project_change_apply_service._resolve_snapshot(
                session, change.project_id, change.target_type, change.target_id
            )
            snapshots.append(current)
        except NotFoundError:
            pass
    return all(
        visible_in_scope(snapshot.get("agent_visibility", AgentVisibility.ALL), scope)
        for snapshot in snapshots
        if isinstance(snapshot, dict)
    )


def _pending_result(change: Any, *, full: bool) -> dict[str, Any]:
    snapshot = change.after or change.before or {}
    timestamp = change.updated_at
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    result = {
        "id": change.id,
        "target_type": change.target_type,
        "target_id": change.target_id,
        "operation": change.operation,
        "status": change.status,
        "title": snapshot.get("title", ""),
        "document_type": snapshot.get("document_type"),
        "updated_at": timestamp.isoformat(),
        "changed_fields": [
            field
            for field in ("title", "body", "agent_visibility", "section")
            if (change.before or {}).get(field) != (change.after or {}).get(field)
        ],
    }
    if full:
        result.update(before=change.before, after=change.after)
    return result


@ToolRegistry.register
class ListPendingProjectChangesTool(AgentTool):
    name: str = "list_pending_project_changes"
    description: str = "列出当前知识范围内的待审资料提案；继续修改已有提案前先查找其 ID。"
    access_level: str = "readonly"
    args_schema: type[BaseModel] = _ProposalInput

    async def _execute(self) -> str:
        session = await create_session()
        try:
            changes = await pending_project_change_service.list_pending_changes(
                session, _pending_project_id(self), "pending"
            )
            visible = [
                _pending_result(change, full=False)
                for change in changes
                if await _pending_visible(self, session, change)
            ]
            return json.dumps({"pending_changes": visible}, ensure_ascii=False)
        finally:
            await session.close()


@ToolRegistry.register
class ReadPendingProjectChangeTool(AgentTool):
    name: str = "read_pending_project_change"
    description: str = (
        "读取一条资料提案的原始快照 before、当前待采用版本 after 和修订版本 updated_at。"
    )
    access_level: str = "readonly"
    args_schema: type[BaseModel] = ReadPendingProjectChangeInput

    async def _execute(self, change_id: str) -> str:
        session = await create_session()
        try:
            change = await pending_project_change_service.get_pending_change(
                session, _pending_project_id(self), change_id
            )
            if not await _pending_visible(self, session, change):
                raise ToolExecutionError("提案不在当前知识范围内")
            return json.dumps(_pending_result(change, full=True), ensure_ascii=False)
        finally:
            await session.close()


@ToolRegistry.register
class RevisePendingProjectChangeTool(AgentTool):
    name: str = "revise_pending_project_change"
    description: str = (
        "继续修订同一条待审提案，不新建提案、不写入正式资料、不自动采用。"
        "先读取提案，以 after 为编辑基础，并传回 updated_at。"
    )
    access_level: str = "write"
    args_schema: type[BaseModel] = RevisePendingProjectChangeInput

    async def _execute(
        self,
        change_id: str,
        expected_updated_at: datetime,
        patch: ProjectChangePatch | dict[str, Any],
    ) -> str:
        session = await create_session()
        try:
            project_id = _pending_project_id(self)
            change = await pending_project_change_service.get_pending_change(
                session, project_id, change_id
            )
            if not await _pending_visible(self, session, change):
                raise ToolExecutionError("提案不在当前知识范围内")
            change = await pending_project_change_service.revise_pending_change(
                session,
                project_id,
                change_id,
                patch=patch.model_dump(exclude_none=True)
                if isinstance(patch, ProjectChangePatch)
                else patch,
                expected_updated_at=expected_updated_at,
            )
            await session.commit()
            return json.dumps(
                {
                    "success": True,
                    "pending_change_id": change.id,
                    "pending_change": _pending_result(change, full=False),
                    "message": "待采用版本已修订，仍待审核。",
                },
                ensure_ascii=False,
            )
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
