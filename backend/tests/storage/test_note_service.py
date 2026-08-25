# -*- coding: utf-8 -*-
"""note_service 服务层测试。"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models.note import Note
from app.storage.models.project import Project
from app.storage.repos import note_category_repo, note_repo
from app.storage.services import note_service


async def _create_project(session: AsyncSession) -> Project:
    project = Project(title="测试项目", description="")
    session.add(project)
    await session.flush()
    return project


@pytest.mark.asyncio
async def test_create_note_at_root_level(session: AsyncSession) -> None:
    project = await _create_project(session)
    note = await note_service.create_note(
        session, project.id, category_id=None, title="根笔记", content="内容"
    )
    assert note.id is not None
    assert note.project_id == project.id
    assert note.category_id is None
    assert note.title == "根笔记"
    assert note.content == "内容"
    assert note.order == 1
    assert note.is_writing_visible is True


@pytest.mark.asyncio
async def test_create_notes_and_categories_append_within_each_parent(
    session: AsyncSession,
) -> None:
    project = await _create_project(session)
    first_category = await note_service.create_category(
        session, project.id, parent_id=None, title="第一类"
    )
    second_category = await note_service.create_category(
        session, project.id, parent_id=None, title="第二类"
    )
    first_note = await note_service.create_note(
        session, project.id, category_id=first_category.id, title="第一条"
    )
    second_note = await note_service.create_note(
        session, project.id, category_id=first_category.id, title="第二条"
    )
    other_note = await note_service.create_note(
        session, project.id, category_id=second_category.id, title="另一类第一条"
    )

    assert (first_category.order, second_category.order) == (1, 2)
    assert (first_note.order, second_note.order) == (1, 2)
    assert other_note.order == 1


@pytest.mark.asyncio
async def test_move_note_appends_to_target_category(session: AsyncSession) -> None:
    project = await _create_project(session)
    source = await note_service.create_category(
        session, project.id, parent_id=None, title="来源"
    )
    target = await note_service.create_category(
        session, project.id, parent_id=None, title="目标"
    )
    existing = await note_service.create_note(
        session, project.id, category_id=target.id, title="目标已有"
    )
    moving = await note_service.create_note(
        session, project.id, category_id=source.id, title="待移动"
    )

    moved = await note_service.move_item(session, "note", moving.id, target.id)

    assert existing.order == 1
    assert moved.category_id == target.id
    assert moved.order == 2


@pytest.mark.asyncio
async def test_create_note_in_first_level_category(session: AsyncSession) -> None:
    project = await _create_project(session)
    cat = await note_service.create_category(
        session, project.id, parent_id=None, title="一级分类"
    )
    note = await note_service.create_note(
        session, project.id, category_id=cat.id, title="子笔记", content=""
    )
    assert note.category_id == cat.id


@pytest.mark.asyncio
async def test_create_note_in_second_level_category(session: AsyncSession) -> None:
    project = await _create_project(session)
    parent = await note_service.create_category(
        session, project.id, parent_id=None, title="一级"
    )
    child = await note_service.create_category(
        session, project.id, parent_id=parent.id, title="二级"
    )
    note = await note_service.create_note(
        session, project.id, category_id=child.id, title="二级下笔记", content=""
    )
    assert note.category_id == child.id


@pytest.mark.asyncio
async def test_create_category_third_level_rejected(session: AsyncSession) -> None:
    project = await _create_project(session)
    parent = await note_service.create_category(
        session, project.id, parent_id=None, title="一级"
    )
    child = await note_service.create_category(
        session, project.id, parent_id=parent.id, title="二级"
    )
    with pytest.raises(ValueError, match="层级不能超过两级"):
        await note_service.create_category(
            session, project.id, parent_id=child.id, title="三级"
        )


@pytest.mark.asyncio
async def test_move_category_self_reference_rejected(session: AsyncSession) -> None:
    project = await _create_project(session)
    cat = await note_service.create_category(
        session, project.id, parent_id=None, title="分类A"
    )
    with pytest.raises(ValueError, match="自身或其后代"):
        await note_service.move_item(session, "category", cat.id, cat.id)


@pytest.mark.asyncio
async def test_move_category_descendant_reference_rejected(
    session: AsyncSession,
) -> None:
    project = await _create_project(session)
    parent = await note_service.create_category(
        session, project.id, parent_id=None, title="父"
    )
    child = await note_service.create_category(
        session, project.id, parent_id=parent.id, title="子"
    )
    with pytest.raises(ValueError, match="自身或其后代"):
        await note_service.move_item(session, "category", parent.id, child.id)


@pytest.mark.asyncio
async def test_move_category_second_level_to_root(session: AsyncSession) -> None:
    project = await _create_project(session)
    parent = await note_service.create_category(
        session, project.id, parent_id=None, title="一级"
    )
    child = await note_service.create_category(
        session, project.id, parent_id=parent.id, title="二级"
    )
    moved = await note_service.move_item(session, "category", child.id, None)
    assert moved.parent_id is None


@pytest.mark.asyncio
async def test_hidden_notes_not_returned_in_list_notes_tool_mode(
    session: AsyncSession,
) -> None:
    project = await _create_project(session)
    hidden_note = Note(
        project_id=project.id,
        category_id=None,
        title="隐藏笔记",
        content="",
        is_hidden=True,
    )
    session.add(hidden_note)
    await session.flush()
    visible_notes = await note_repo.list_by_project(
        session, project.id, include_hidden=False
    )
    assert all(n.is_hidden is False for n in visible_notes)


@pytest.mark.asyncio
async def test_list_notes_tree_structure(session: AsyncSession) -> None:
    project = await _create_project(session)
    cat1 = await note_service.create_category(session, project.id, None, "分类A")
    cat2 = await note_service.create_category(session, project.id, cat1.id, "分类A-子")
    await note_service.create_note(session, project.id, None, "根笔记", "x")
    await note_service.create_note(session, project.id, cat1.id, "A笔记", "x")
    await note_service.create_note(session, project.id, cat2.id, "A-子笔记", "x")

    result = await note_service.list_notes(session, project.id)
    assert result.total_notes == 3
    assert len(result.root_notes) == 1
    assert result.root_notes[0].title == "根笔记"
    assert len(result.categories) == 1
    assert result.categories[0].category.title == "分类A"
    assert len(result.categories[0].sub_categories) == 1
    assert result.categories[0].sub_categories[0].category.title == "分类A-子"
    assert len(result.categories[0].notes) == 1
    assert result.categories[0].notes[0].title == "A笔记"


@pytest.mark.asyncio
async def test_delete_category_cascades_to_children(session: AsyncSession) -> None:
    project = await _create_project(session)
    parent = await note_service.create_category(session, project.id, None, "父")
    child = await note_service.create_category(session, project.id, parent.id, "子")
    await note_service.create_note(session, project.id, child.id, "笔记", "")
    assert await note_category_repo.get_by_id(session, parent.id) is not None
    await note_service.delete_category(session, parent.id)
    assert await note_category_repo.get_by_id(session, parent.id) is None
    assert await note_category_repo.get_by_id(session, child.id) is None
