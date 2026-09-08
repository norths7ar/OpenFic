"""note_service 服务层测试。"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
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
    assert note.agent_visibility == "all"


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
    source = await note_service.create_category(session, project.id, parent_id=None, title="来源")
    target = await note_service.create_category(session, project.id, parent_id=None, title="目标")
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
async def test_locked_note_blocks_content_move_and_delete_but_allows_visibility(
    session: AsyncSession,
) -> None:
    project = await _create_project(session)
    target = await note_service.create_category(session, project.id, parent_id=None, title="目标")
    note = await note_service.create_note(
        session, project.id, category_id=None, title="锁定笔记", content="原文"
    )
    await note_service.set_note_locked(session, note.id, True)

    with pytest.raises(ConflictError, match="已锁定"):
        await note_service.update_note(session, note.id, content="改写")
    with pytest.raises(ConflictError, match="已锁定"):
        await note_service.move_item(session, "note", note.id, target.id)
    with pytest.raises(ConflictError, match="已锁定"):
        await note_service.delete_note(session, note.id)

    updated = await note_service.update_note(session, note.id, agent_visibility="global")
    assert updated.agent_visibility == "global"


@pytest.mark.asyncio
async def test_create_note_in_first_level_category(session: AsyncSession) -> None:
    project = await _create_project(session)
    cat = await note_service.create_category(session, project.id, parent_id=None, title="一级分类")
    note = await note_service.create_note(
        session, project.id, category_id=cat.id, title="子笔记", content=""
    )
    assert note.category_id == cat.id


@pytest.mark.asyncio
async def test_create_nested_category_rejected(session: AsyncSession) -> None:
    project = await _create_project(session)
    parent = await note_service.create_category(session, project.id, parent_id=None, title="一级")
    with pytest.raises(ValueError, match="只支持一层"):
        await note_service.create_category(session, project.id, parent_id=parent.id, title="二级")


@pytest.mark.asyncio
async def test_move_category_into_category_rejected(session: AsyncSession) -> None:
    project = await _create_project(session)
    source = await note_service.create_category(session, project.id, parent_id=None, title="来源")
    target = await note_service.create_category(session, project.id, parent_id=None, title="目标")
    with pytest.raises(ValueError, match="只支持一层"):
        await note_service.move_item(session, "category", source.id, target.id)


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
        agent_visibility="none",
    )
    session.add(hidden_note)
    await session.flush()
    visible_notes = await note_repo.list_by_project(session, project.id, include_hidden=False)
    assert all(n.agent_visibility != "none" for n in visible_notes)


@pytest.mark.asyncio
async def test_list_notes_tree_structure(session: AsyncSession) -> None:
    project = await _create_project(session)
    cat1 = await note_service.create_category(session, project.id, None, "分类A")
    cat2 = await note_service.create_category(session, project.id, None, "分类B")
    await note_service.create_note(session, project.id, None, "根笔记", "x")
    await note_service.create_note(session, project.id, cat1.id, "A笔记", "x")
    await note_service.create_note(session, project.id, cat2.id, "B笔记", "x")

    result = await note_service.list_notes(session, project.id)
    assert result.total_notes == 3
    assert len(result.root_notes) == 1
    assert result.root_notes[0].title == "根笔记"
    assert len(result.categories) == 2
    assert result.categories[0].category.title == "分类A"
    assert result.categories[0].sub_categories == []
    assert len(result.categories[0].notes) == 1
    assert result.categories[0].notes[0].title == "A笔记"


@pytest.mark.asyncio
async def test_delete_folder_appends_contents_to_root_in_order(session: AsyncSession) -> None:
    project = await _create_project(session)
    before = await note_service.create_note(session, project.id, None, "之前", "")
    parent = await note_service.create_category(session, project.id, None, "父")
    direct_note = await note_service.create_note(session, project.id, parent.id, "直属笔记", "")
    locked_note = await note_service.create_note(session, project.id, parent.id, "锁定笔记", "")
    await note_service.set_note_locked(session, locked_note.id, True)
    after = await note_service.create_note(session, project.id, None, "之后", "")
    assert await note_category_repo.get_by_id(session, parent.id) is not None

    await note_service.delete_category(session, parent.id)

    assert await note_category_repo.get_by_id(session, parent.id) is None
    assert (await note_service.get_note(session, direct_note.id)).category_id is None
    assert (await note_service.get_note(session, locked_note.id)).category_id is None

    tree = await note_service.list_notes(session, project.id)
    mixed_root = sorted(
        [
            *(
                (item.order, "category", item.id)
                for item in (node.category for node in tree.categories)
            ),
            *((item.order, "note", item.id) for item in tree.root_notes),
        ]
    )
    assert [(kind, item_id) for _, kind, item_id in mixed_root] == [
        ("note", before.id),
        ("note", after.id),
        ("note", direct_note.id),
        ("note", locked_note.id),
    ]
