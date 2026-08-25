"""Validate, conflict-check, and apply pending project knowledge changes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.project_bundle.export import semantic_hash
from app.storage.models.character import Character
from app.storage.models.note import Note, NoteCategory
from app.storage.models.pending_project_change import PendingProjectChange
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
    writing_visible: bool = True


class _NoteCategoryPayload(_StrictPayload):
    title: str = Field(min_length=1, max_length=200)
    parent_id: None = None


class _CharacterPayload(_StrictPayload):
    title: str = Field(min_length=1, max_length=200)
    body: str = ""
    writing_visible: bool = True


class _WorldEntryPayload(_StrictPayload):
    title: str = Field(min_length=1, max_length=200)
    body: str = ""
    section: str = Field(default="", max_length=500)
    writing_visible: bool = True


@dataclass(frozen=True)
class PreparedPendingChange:
    target_id: str | None
    base_hash: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None


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
        "order": note.order,
        "writing_visible": note.is_writing_visible,
        "is_locked": note.is_locked,
        "is_hidden": note.is_hidden,
        "title": note.title,
        "body": note.content,
    }


def _note_category_snapshot(category: NoteCategory) -> dict[str, Any]:
    return {
        "kind": "note_category",
        "id": category.id,
        "project_id": category.project_id,
        "parent_id": category.parent_id,
        "title": category.title,
        "order": category.order,
    }


def _character_snapshot(character: Character) -> dict[str, Any]:
    return {
        "kind": "character",
        "id": character.id,
        "project_id": character.project_id,
        "order": character.order,
        "writing_visible": character.is_writing_visible,
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
        "writing_visible": entry.is_enabled,
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
            "writing_visible": snapshot["writing_visible"],
        }
    if target_type == "note_category":
        return {"title": snapshot["title"], "parent_id": snapshot["parent_id"]}
    if target_type == "character":
        return {
            "title": snapshot["title"],
            "body": snapshot["body"],
            "writing_visible": snapshot["writing_visible"],
        }
    return {
        "title": snapshot["title"],
        "body": snapshot["body"],
        "section": snapshot["section"],
        "writing_visible": snapshot["writing_visible"],
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
    payload = _validate_payload(target_type, {**base, **patch})
    if current is None:
        return {"kind": target_type, **payload}
    if target_type == "note" and payload["category_id"] != current["category_id"]:
        raise ValidationError("待审变更不能移动笔记分类")
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
        notes = await note_repo.list_by_project(
            session, project_id, include_hidden=True
        )
        if any(
            note.category_id == after["category_id"] and note.title == title
            for note in notes
        ):
            raise PendingChangeConflictError("同级笔记标题已存在")
        category_id = after["category_id"]
        if category_id is not None:
            category = await note_category_repo.get_by_id(session, category_id)
            if category is None or category.project_id != project_id:
                raise PendingChangeConflictError("笔记分类不存在或不属于当前项目")
        return
    if target_type == "note_category":
        categories = await note_category_repo.list_by_project(session, project_id)
        if any(
            category.parent_id is None and category.title == title
            for category in categories
        ):
            raise PendingChangeConflictError("顶层笔记分类标题已存在")
        return
    if target_type == "character":
        if await character_repo.name_exists(session, project_id, title):
            raise PendingChangeConflictError("角色名称已存在")
        return
    world_info = await world_info_service.get_or_create_world_info_by_project(
        session, project_id
    )
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
        )
        if not after["writing_visible"]:
            note = await note_service.update_note(
                session, note.id, is_writing_visible=False
            )
        return note.id, _note_snapshot(note)
    if target_type == "note_category":
        category = await note_service.create_category(
            session,
            project_id,
            None,
            after["title"],
        )
        return category.id, _note_category_snapshot(category)
    if target_type == "character":
        character = await character_service.create_character(
            session,
            project_id,
            after["title"],
            after["body"],
        )
        if not after["writing_visible"]:
            character = await character_service.update_character(
                session,
                character.id,
                is_writing_visible=False,
            )
        return character.id, _character_snapshot(character)
    world_info = await world_info_service.get_or_create_world_info_by_project(
        session, project_id
    )
    entry = await world_info_entry_service.create_entry(
        session,
        world_info.id,
        after["title"],
        content=after["body"],
        token_count=world_info_entry_service.calculate_token_count(after["body"]),
        is_enabled=after["writing_visible"],
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
            is_writing_visible=after["writing_visible"],
        )
        return _note_snapshot(updated)
    if target_type == "note_category":
        category = target
        if not isinstance(category, NoteCategory):
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
                is_writing_visible=after["writing_visible"],
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
            is_enabled=after["writing_visible"],
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
