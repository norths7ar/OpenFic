"""
ProjectFolder Service - 卷业务逻辑层。
"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.storage.models.project_folder import ProjectFolder
from app.storage.repos import chapter_repo, project_repo, volume_repo
from app.storage.services import project_folder_service

DEFAULT_VOLUME_TITLE = "第一卷"
UNSET = object()


async def create_default_volume(session: AsyncSession, project_id: str) -> ProjectFolder:
    """为项目创建默认卷。"""
    volume = ProjectFolder(
        scope="writing",
        project_id=project_id,
        title=DEFAULT_VOLUME_TITLE,
        description=None,
        order=1,
        item_count=0,
    )
    return await volume_repo.create(session, volume)


async def create_volume(
    session: AsyncSession,
    project_id: str,
    title: str,
    description: str | None = None,
) -> ProjectFolder:
    """在项目末尾追加卷。"""
    project = await project_repo.get_by_id(session, project_id)
    if project is None:
        raise NotFoundError(f"项目不存在: {project_id}")

    max_order = await volume_repo.get_max_order(session, project_id)
    volume = ProjectFolder(
        scope="writing",
        project_id=project_id,
        title=title,
        description=description,
        order=max_order + 1,
        item_count=0,
    )
    return await volume_repo.create(session, volume)


async def get_volume(session: AsyncSession, volume_id: str) -> ProjectFolder:
    """获取卷详情。"""
    volume = await volume_repo.get_by_id(session, volume_id)
    if volume is None:
        raise NotFoundError(f"卷不存在: {volume_id}")
    return volume


async def list_volumes(session: AsyncSession, project_id: str) -> list[ProjectFolder]:
    """列出项目下全部卷。"""
    project = await project_repo.get_by_id(session, project_id)
    if project is None:
        raise NotFoundError(f"项目不存在: {project_id}")
    return await volume_repo.list_by_project(session, project_id)


async def update_volume(
    session: AsyncSession,
    volume_id: str,
    title: str | None = None,
    description: str | None | object = UNSET,
) -> ProjectFolder:
    """更新卷。"""
    volume = await get_volume(session, volume_id)
    changed = False
    if title is not None and title != volume.title:
        volume.title = title
        changed = True
    if description is not UNSET and description != volume.description:
        volume.description = description if isinstance(description, str) else None
        changed = True
    if changed:
        volume.updated_at = datetime.now(UTC)
        volume = await volume_repo.update_volume(session, volume)
    return volume


async def refresh_volume_chapter_count(
    session: AsyncSession,
    volume_id: str,
) -> ProjectFolder | None:
    """刷新卷章节数缓存。"""
    volume = await volume_repo.get_by_id(session, volume_id)
    if volume is None:
        return None
    volume.item_count = await chapter_repo.count_by_volume(session, volume_id)
    volume.updated_at = datetime.now(UTC)
    return await volume_repo.update_volume(session, volume)


async def delete_volume(
    session: AsyncSession,
    volume_id: str,
    *,
    cascade: bool = False,
) -> None:
    """Compatibility endpoint: deleting a writing folder promotes its chapters."""
    await get_volume(session, volume_id)
    await project_folder_service.delete_folder(session, volume_id)


async def move_volume(
    session: AsyncSession,
    volume_id: str,
    new_order: int,
) -> ProjectFolder:
    """调整卷顺序。"""
    volume = await get_volume(session, volume_id)
    folders = await volume_repo.list_by_project(session, volume.project_id)
    if new_order < 1 or new_order > len(folders):
        raise ValueError(f"无效的排序位置: {new_order}")
    ids = [folder.id for folder in folders if folder.id != volume_id]
    ids.insert(new_order - 1, volume_id)
    await project_folder_service.reorder_folders(session, volume.project_id, "writing", ids)
    return await get_volume(session, volume_id)
