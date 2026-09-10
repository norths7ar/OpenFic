"""Validate, conflict-check, and apply pending project knowledge changes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_visibility import AgentVisibility
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.project_bundle.export import semantic_hash
from app.storage.history_capture import with_history_source
from app.storage.models.character import Character
from app.storage.models.note import Note
from app.storage.models.pending_project_change import PendingProjectChange
from app.storage.models.project_folder import ProjectFolder
from app.storage.models.world_info_entry import WorldInfoEntry
from app.storage.repos import (
    character_repo,
    note_category_repo,
    note_repo,
    pending_project_change_repo,
    world_info_entry_repo,
    world_info_repo,
)
from app.storage.services import (
    character_service,
    note_service,
    world_info_entry_service,
    world_info_service,
)

PendingTargetType = Literal["note", "note_category", "character", "world_entry"]


class _StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _NotePayload(_StrictPayload):
    title: str = Field(min_length=1, max_length=200)
    body: str = ""
    category_id: str | None = None
    agent_visibility: AgentVisibility = AgentVisibility.ALL
    document_type: Literal["note", "outline"] = "note"


class _NoteCategoryPayload(_StrictPayload):
    title: str = Field(min_length=1, max_length=200)
    parent_id: None = None
    document_type: Literal["note", "outline"] = "note"


class _CharacterPayload(_StrictPayload):
    title: str = Field(min_length=1, max_length=200)
    body: str = ""
    agent_visibility: AgentVisibility = AgentVisibility.ALL


class _WorldEntryPayload(_StrictPayload):
    title: str = Field(min_length=1, max_length=200)
    body: str = ""
    section: str = Field(default="", max_length=500)
    agent_visibility: AgentVisibility = AgentVisibility.ALL


@dataclass(frozen=True)
class PreparedPendingChange:
    target_id: str | None
    base_hash: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None


@dataclass(frozen=True)
class PendingChangeApplicability:
    is_applicable: bool
    reason: str | None = None


class PendingChangeConflictError(ConflictError):
    """The target changed, disappeared, or cannot be applied without ambiguity."""

    def __init__(
        self,
        message: str,
        *,
        current: dict[str, Any] | None = None,
        current_hash: str | None = None,
    ) -> None:
        super().__init__(message)
        self.current = current
        self.current_hash = current_hash


def _snapshot_hash(snapshot: dict[str, Any]) -> str:
    return semantic_hash(snapshot)


def _note_snapshot(note: Note) -> dict[str, Any]:
    return {
        "kind": "note",
        "id": note.id,
        "project_id": note.project_id,
        "category_id": note.category_id,
        "document_type": note.document_type,
        "order": note.order,
        "agent_visibility": note.agent_visibility,
        "is_locked": note.is_locked,
        "title": note.title,
        "body": note.content,
    }


def _note_category_snapshot(category: ProjectFolder) -> dict[str, Any]:
    return {
        "kind": "note_category",
        "id": category.id,
        "project_id": category.project_id,
        "parent_id": None,
        "document_type": category.scope,
        "title": category.title,
        "order": category.order,
    }


def _character_snapshot(character: Character) -> dict[str, Any]:
    return {
        "kind": "character",
        "id": character.id,
        "project_id": character.project_id,
        "order": character.order,
        "agent_visibility": character.agent_visibility,
        "is_favorited": character.is_favorited,
        "title": character.name,
        "body": character.description,
    }


async def _world_entry_snapshot(
    session: AsyncSession,
    entry: WorldInfoEntry,
    project_id: str,
) -> dict[str, Any]:
    world_info = await world_info_repo.get_by_id(session, entry.world_info_id)
    if world_info is None or world_info.project_id != project_id:
        raise NotFoundError("待审变更目标不存在")
    return {
        "kind": "world_entry",
        "id": entry.id,
        "project_id": project_id,
        "world_info_id": entry.world_info_id,
        "uid": entry.uid,
        "section": entry.section,
        "order": entry.order,
        "agent_visibility": entry.agent_visibility,
        "title": entry.name,
        "body": entry.content,
    }


async def _resolve_snapshot(
    session: AsyncSession,
    project_id: str,
    target_type: PendingTargetType,
    target_id: str,
) -> tuple[object, dict[str, Any]]:
    if target_type == "note":
        target = await note_repo.get_by_id(session, target_id)
        if target is None or target.project_id != project_id:
            raise NotFoundError("待审变更目标不存在")
        return target, _note_snapshot(target)
    if target_type == "note_category":
        target = await note_category_repo.get_by_id(session, target_id)
        if target is None or target.project_id != project_id:
            raise NotFoundError("待审变更目标不存在")
        return target, _note_category_snapshot(target)
    if target_type == "character":
        target = await character_repo.get_by_id(session, target_id)
        if target is None or target.project_id != project_id:
            raise NotFoundError("待审变更目标不存在")
        return target, _character_snapshot(target)
    target = await world_info_entry_repo.get_by_id(session, target_id)
    if target is None:
        raise NotFoundError("待审变更目标不存在")
    return target, await _world_entry_snapshot(session, target, project_id)


def _payload_model(target_type: PendingTargetType) -> type[_StrictPayload]:
    return {
        "note": _NotePayload,
        "note_category": _NoteCategoryPayload,
        "character": _CharacterPayload,
        "world_entry": _WorldEntryPayload,
    }[target_type]


def _editable_payload(
    target_type: PendingTargetType,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    if target_type == "note":
        return {
            "title": snapshot["title"],
            "body": snapshot["body"],
            "category_id": snapshot["category_id"],
            "document_type": snapshot["document_type"],
            "agent_visibility": snapshot["agent_visibility"],
        }
    if target_type == "note_category":
        return {
            "title": snapshot["title"],
            "parent_id": snapshot["parent_id"],
            "document_type": snapshot["document_type"],
        }
    if target_type == "character":
        return {
            "title": snapshot["title"],
            "body": snapshot["body"],
            "agent_visibility": snapshot["agent_visibility"],
        }
    return {
        "title": snapshot["title"],
        "body": snapshot["body"],
        "section": snapshot["section"],
        "agent_visibility": snapshot["agent_visibility"],
    }


def _validate_payload(
    target_type: PendingTargetType,
    value: object,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError("after 必须是对象")
    try:
        payload = _payload_model(target_type).model_validate(value).model_dump()
    except PydanticValidationError as exc:
        raise ValidationError(f"待审变更内容无效: {exc}") from exc
    if target_type == "character":
        payload["title"] = payload["title"].strip()
        if not payload["title"]:
            raise ValidationError("角色名不能为空")
    return payload


def _prepare_after(
    target_type: PendingTargetType,
    patch: object,
    current: dict[str, Any] | None,
) -> dict[str, Any]:
    base = _editable_payload(target_type, current) if current is not None else {}
    if not isinstance(patch, dict):
        raise ValidationError("after 必须是对象")
    patch_data = cast(dict[str, Any], patch)
    if "kind" in patch_data and patch_data["kind"] != target_type:
        raise ValidationError("after.kind 必须与 target_type 一致")
    editable_patch = {key: value for key, value in patch_data.items() if key != "kind"}
    edits = editable_patch.pop("edits", None)
    if edits is not None:
        if current is None or target_type == "note_category":
            raise ValidationError("edits 只适用于修改资料正文")
        if editable_patch.get("body") is not None:
            raise ValidationError("body 和 edits 不能同时提供")
        if not isinstance(edits, list) or not edits:
            raise ValidationError("edits 必须是非空替换列表")
        body = str(base["body"])
        for index, edit in enumerate(edits, 1):
            if not isinstance(edit, dict):
                raise ValidationError(f"第 {index} 处替换必须是对象")
            edit = cast(dict[str, Any], edit)
            if (
                set(edit) != {"old_content", "new_content"}
                or not isinstance(edit["old_content"], str)
                or not edit["old_content"]
                or not isinstance(edit["new_content"], str)
            ):
                raise ValidationError(
                    f"第 {index} 处替换必须提供非空 old_content 和字符串 new_content"
                )
            old = edit["old_content"]
            count = body.count(old)
            # Count overlapping occurrences too: 'aa' in 'aaa' is ambiguous.
            first = body.find(old)
            if count == 0:
                raise ValidationError(f"第 {index} 处原片段未找到，请重新读取当前正文")
            if body.find(old, first + 1) != -1:
                raise ValidationError(f"第 {index} 处原片段匹配多处，请提供更多上下文")
            body = body.replace(old, edit["new_content"], 1)
        editable_patch["body"] = body
    payload = _validate_payload(target_type, {**base, **editable_patch})
    if current is None:
        return {"kind": target_type, **payload}
    if target_type == "note" and payload["category_id"] != current["category_id"]:
        raise ValidationError("待审变更不能移动笔记分类")
    if target_type in {"note", "note_category"} and (
        payload["document_type"] != current["document_type"]
    ):
        raise ValidationError("待审变更不能改变文档类型")
    if target_type == "note_category" and payload["parent_id"] != current["parent_id"]:
        raise ValidationError("待审变更不能移动笔记分类")
    return {**current, **payload}


async def prepare_pending_change(
    session: AsyncSession,
    *,
    project_id: str,
    target_type: PendingTargetType,
    target_id: str | None,
    operation: str,
    after: object,
) -> PreparedPendingChange:
    """Capture the authoritative base snapshot and normalize the proposed result."""
    if operation == "create":
        if target_id is not None:
            raise ValidationError("create 不能指定 target_id")
        normalized_after = _prepare_after(target_type, after, None)
        if target_type == "note_category" and normalized_after["parent_id"] is not None:
            raise ValidationError("待审变更第一版仅支持创建顶层笔记分类")
        return PreparedPendingChange(None, None, None, normalized_after)
    if operation not in {"update", "delete"}:
        raise ValidationError(f"不支持的待审变更操作: {operation}")
    if not target_id:
        raise ValidationError(f"{operation} 必须指定 target_id")
    if target_type == "note_category" and operation == "delete":
        raise ValidationError("待审变更不支持级联删除笔记分类")

    _target, current = await _resolve_snapshot(
        session,
        project_id,
        target_type,
        target_id,
    )
    if operation == "delete":
        if after is not None:
            raise ValidationError("delete 的 after 必须为空")
        normalized_after = None
    else:
        normalized_after = _prepare_after(target_type, after, current)
    return PreparedPendingChange(
        target_id=target_id,
        base_hash=_snapshot_hash(current),
        before=current,
        after=normalized_after,
    )


def _validate_stored_after(
    target_type: PendingTargetType,
    operation: str,
    after: object,
    current: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if operation == "delete":
        if after is not None:
            raise ValidationError("delete 的 after 必须为空")
        return None
    if not isinstance(after, dict) or after.get("kind") != target_type:
        raise ValidationError("候审结果格式无效")
    after_record = cast(dict[str, Any], after)
    if current is None:
        expected = {"kind", *_payload_model(target_type).model_fields}
        if set(after_record) != expected:
            raise ValidationError("候审结果包含未授权字段")
        payload = _validate_payload(
            target_type,
            {k: v for k, v in after_record.items() if k != "kind"},
        )
        return {"kind": target_type, **payload}

    if set(after_record) != set(current):
        raise ValidationError("候审结果字段与当前对象不一致")
    editable_keys = set(_editable_payload(target_type, current))
    immutable_keys = set(current) - editable_keys
    if any(after_record[key] != current[key] for key in immutable_keys):
        raise ValidationError("候审结果试图修改服务端管理字段")
    payload = _validate_payload(
        target_type,
        {key: after_record[key] for key in editable_keys},
    )
    return {**current, **payload}


async def _assert_create_name_available(
    session: AsyncSession,
    project_id: str,
    target_type: PendingTargetType,
    after: dict[str, Any],
) -> None:
    title = str(after["title"])
    if target_type == "note":
        notes = await note_repo.list_by_project(session, project_id, include_hidden=True)
        if any(note.category_id == after["category_id"] and note.title == title for note in notes):
            raise PendingChangeConflictError("同级笔记标题已存在")
        category_id = after["category_id"]
        if category_id is not None:
            category = await note_category_repo.get_by_id(session, category_id)
            if category is None or category.project_id != project_id:
                raise PendingChangeConflictError("笔记分类不存在或不属于当前项目")
        return
    if target_type == "note_category":
        return
    if target_type == "character":
        if await character_repo.name_exists(session, project_id, title):
            raise PendingChangeConflictError("角色名称已存在")
        return
    world_info = await world_info_service.get_or_create_world_info_by_project(session, project_id)
    try:
        await world_info_entry_service.ensure_entry_name_available(
            session,
            world_info.id,
            title,
        )
    except ValueError as exc:
        raise PendingChangeConflictError(str(exc)) from exc


async def _apply_create(
    session: AsyncSession,
    project_id: str,
    target_type: PendingTargetType,
    after: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    await _assert_create_name_available(session, project_id, target_type, after)
    if target_type == "note":
        note = await note_service.create_note(
            session,
            project_id,
            after["category_id"],
            after["title"],
            after["body"],
            after["document_type"],
        )
        if after["agent_visibility"] != AgentVisibility.ALL:
            note = await note_service.update_note(
                session, note.id, agent_visibility=after["agent_visibility"]
            )
        return note.id, _note_snapshot(note)
    if target_type == "note_category":
        category = await note_service.create_category(
            session,
            project_id,
            None,
            after["title"],
            after["document_type"],
        )
        return category.id, _note_category_snapshot(category)
    if target_type == "character":
        character = await character_service.create_character(
            session,
            project_id,
            after["title"],
            after["body"],
        )
        if after["agent_visibility"] != AgentVisibility.ALL:
            character = await character_service.update_character(
                session,
                character.id,
                agent_visibility=after["agent_visibility"],
            )
        return character.id, _character_snapshot(character)
    world_info = await world_info_service.get_or_create_world_info_by_project(session, project_id)
    entry = await world_info_entry_service.create_entry(
        session,
        world_info.id,
        after["title"],
        content=after["body"],
        token_count=world_info_entry_service.calculate_token_count(after["body"]),
        agent_visibility=after["agent_visibility"],
        section=after["section"],
    )
    return entry.id, await _world_entry_snapshot(session, entry, project_id)


async def _apply_update(
    session: AsyncSession,
    project_id: str,
    target_type: PendingTargetType,
    target: object,
    after: dict[str, Any],
) -> dict[str, Any]:
    if target_type == "note":
        note = target
        if not isinstance(note, Note):
            raise ValidationError("待审变更目标类型错误")
        if note.is_locked:
            raise PendingChangeConflictError("笔记已锁定，请先解锁")
        updated = await note_service.update_note(
            session,
            note.id,
            title=after["title"],
            content=after["body"],
            agent_visibility=after["agent_visibility"],
        )
        return _note_snapshot(updated)
    if target_type == "note_category":
        category = target
        if not isinstance(category, ProjectFolder):
            raise ValidationError("待审变更目标类型错误")
        updated = await note_service.update_category(
            session,
            category.id,
            after["title"],
        )
        return _note_category_snapshot(updated)
    if target_type == "character":
        character = target
        if not isinstance(character, Character):
            raise ValidationError("待审变更目标类型错误")
        try:
            updated = await character_service.update_character(
                session,
                character.id,
                name=after["title"],
                description=after["body"],
                agent_visibility=after["agent_visibility"],
            )
        except ConflictError as exc:
            raise PendingChangeConflictError(str(exc)) from exc
        return _character_snapshot(updated)
    entry = target
    if not isinstance(entry, WorldInfoEntry):
        raise ValidationError("待审变更目标类型错误")
    try:
        updated = await world_info_entry_service.update_entry(
            session,
            entry.id,
            name=after["title"],
            content=after["body"],
            token_count=world_info_entry_service.calculate_token_count(after["body"]),
            agent_visibility=after["agent_visibility"],
            section=after["section"],
        )
    except ValueError as exc:
        raise PendingChangeConflictError(str(exc)) from exc
    return await _world_entry_snapshot(session, updated, project_id)


async def _apply_delete(
    session: AsyncSession,
    target_type: PendingTargetType,
    target: object,
) -> None:
    if target_type == "note":
        note = target
        if not isinstance(note, Note):
            raise ValidationError("待审变更目标类型错误")
        if note.is_locked:
            raise PendingChangeConflictError("笔记已锁定，请先解锁")
        await note_service.delete_note(session, note.id)
        return
    if target_type == "note_category":
        raise ValidationError("待审变更不支持级联删除笔记分类")
    if target_type == "character":
        character = target
        if not isinstance(character, Character):
            raise ValidationError("待审变更目标类型错误")
        await character_service.delete_character(session, character.id)
        return
    entry = target
    if not isinstance(entry, WorldInfoEntry):
        raise ValidationError("待审变更目标类型错误")
    await world_info_entry_service.delete_entry(session, entry.id)


async def assess_pending_change(
    session: AsyncSession,
    change: PendingProjectChange,
) -> PendingChangeApplicability:
    """Validate whether a stored proposal can currently enter the apply path."""
    if change.status != "pending":
        return PendingChangeApplicability(False, "只有待审状态的变更可以采用")
    if change.target_type not in {"note", "note_category", "character", "world_entry"}:
        return PendingChangeApplicability(False, "不支持的待审变更目标")
    target_type = cast(PendingTargetType, change.target_type)
    try:
        if change.operation == "create":
            if (
                change.target_id is not None
                or change.base_hash is not None
                or change.before is not None
            ):
                raise ValidationError("create 候审变更的基础状态无效")
            stored_after = _validate_stored_after(
                target_type,
                change.operation,
                change.after,
                None,
            )
            if stored_after is None:
                raise ValidationError("create 缺少 after")
            return PendingChangeApplicability(True)

        if change.operation not in {"update", "delete"}:
            raise ValidationError(f"不支持的待审变更操作: {change.operation}")
        if not change.target_id or not change.base_hash:
            raise ValidationError(f"{change.operation} 缺少目标或 base_hash")
        target, current = await _resolve_snapshot(
            session,
            change.project_id,
            target_type,
            change.target_id,
        )
        if _snapshot_hash(current) != change.base_hash:
            return PendingChangeApplicability(False, "正式资料已在候审后发生变化")
        _validate_stored_after(
            target_type,
            change.operation,
            change.after,
            current,
        )
        if target_type == "note" and isinstance(target, Note) and target.is_locked:
            return PendingChangeApplicability(False, "笔记已锁定，请先解锁")
        return PendingChangeApplicability(True)
    except NotFoundError:
        return PendingChangeApplicability(False, "候审目标已不存在")
    except ValidationError as exc:
        return PendingChangeApplicability(False, str(exc))


@with_history_source("ai")
async def apply_pending_change(
    session: AsyncSession,
    change: PendingProjectChange,
) -> PendingProjectChange:
    """Apply one pending change atomically after checking its captured base hash."""
    claimed = await pending_project_change_repo.claim_for_apply(
        session,
        change.project_id,
        change.id,
    )
    if not claimed:
        raise PendingChangeConflictError("只有待审状态的变更可以采用")
    await session.refresh(change)
    if change.target_type not in {"note", "note_category", "character", "world_entry"}:
        raise ValidationError(f"不支持的待审变更目标: {change.target_type}")
    target_type = cast(PendingTargetType, change.target_type)

    if change.operation == "create":
        if (
            change.target_id is not None
            or change.base_hash is not None
            or change.before is not None
        ):
            raise ValidationError("create 候审变更的基础状态无效")
        normalized_after = _validate_stored_after(
            target_type,
            change.operation,
            change.after,
            None,
        )
        if normalized_after is None:
            raise ValidationError("create 缺少 after")
        target_id, applied_snapshot = await _apply_create(
            session,
            change.project_id,
            target_type,
            normalized_after,
        )
        change.target_id = target_id
        change.after = applied_snapshot
    else:
        if not change.target_id or not change.base_hash:
            raise ValidationError(f"{change.operation} 缺少目标或 base_hash")
        try:
            target, current = await _resolve_snapshot(
                session,
                change.project_id,
                target_type,
                change.target_id,
            )
        except NotFoundError as exc:
            raise PendingChangeConflictError("候审目标已不存在") from exc
        current_hash = _snapshot_hash(current)
        if current_hash != change.base_hash:
            raise PendingChangeConflictError(
                "正式资料已在候审后发生变化",
                current=current,
                current_hash=current_hash,
            )
        normalized_after = _validate_stored_after(
            target_type,
            change.operation,
            change.after,
            current,
        )
        if change.operation == "update":
            if normalized_after is None:
                raise ValidationError("update 缺少 after")
            change.after = await _apply_update(
                session,
                change.project_id,
                target_type,
                target,
                normalized_after,
            )
        elif change.operation == "delete":
            await _apply_delete(session, target_type, target)
        else:
            raise ValidationError(f"不支持的待审变更操作: {change.operation}")

    now = datetime.now(UTC)
    change.status = "applied"
    change.applied_at = now
    change.updated_at = now
    return await pending_project_change_repo.update(session, change)
