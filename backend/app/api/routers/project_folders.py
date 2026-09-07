"""Shared project-folder CRUD endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.project_folder import (
    ProjectFolderCreate,
    ProjectFolderItemMove,
    ProjectFolderListResponse,
    ProjectFolderReorder,
    ProjectFolderResponse,
    ProjectFolderScope,
    ProjectFolderUpdate,
)
from app.background.jobs import service as background_service
from app.storage.database import get_session
from app.storage.services import project_folder_service

router = APIRouter(tags=["project-folders"])


@router.get(
    "/projects/{project_id}/folders",
    response_model=ProjectFolderListResponse,
)
async def list_project_folders(
    project_id: str,
    scope: Annotated[ProjectFolderScope, Query()],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProjectFolderListResponse:
    folders = await project_folder_service.list_folders(session, project_id, scope)
    return ProjectFolderListResponse(
        items=[ProjectFolderResponse.model_validate(folder) for folder in folders]
    )


@router.post(
    "/projects/{project_id}/folders",
    response_model=ProjectFolderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_folder(
    project_id: str,
    data: ProjectFolderCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProjectFolderResponse:
    folder = await project_folder_service.create_folder(
        session, project_id, data.scope, data.title, data.description
    )
    await background_service.commit_and_notify(session)
    return ProjectFolderResponse.model_validate(folder)


@router.patch("/folders/{folder_id}", response_model=ProjectFolderResponse)
async def update_project_folder(
    folder_id: str,
    data: ProjectFolderUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProjectFolderResponse:
    folder = await project_folder_service.update_folder(
        session,
        folder_id,
        data.title,
        data.description
        if "description" in data.model_fields_set
        else project_folder_service.UNSET,
    )
    await background_service.commit_and_notify(session)
    return ProjectFolderResponse.model_validate(folder)


@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_folder(
    folder_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    await project_folder_service.delete_folder(session, folder_id)
    await background_service.commit_and_notify(session)


@router.post("/projects/{project_id}/folders/items/move", status_code=status.HTTP_204_NO_CONTENT)
async def move_project_folder_item(
    project_id: str,
    data: ProjectFolderItemMove,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    await project_folder_service.move_item(
        session,
        project_id,
        data.scope,
        data.item_id,
        data.folder_id,
    )
    await background_service.commit_and_notify(session)


@router.post("/projects/{project_id}/folders/reorder")
async def reorder_project_folders(
    project_id: str,
    data: ProjectFolderReorder,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, int]:
    updated_count = await project_folder_service.reorder_folders(
        session, project_id, data.scope, data.ordered_ids
    )
    await background_service.commit_and_notify(session)
    return {"updated_count": updated_count}
