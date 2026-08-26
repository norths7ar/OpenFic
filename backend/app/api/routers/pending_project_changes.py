"""待审项目变更 API。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.pending_project_change import (
    PendingProjectChangeCreate,
    PendingProjectChangeResponse,
    PendingProjectChangeStatus,
)
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.storage.database import get_session
from app.storage.models.pending_project_change import PendingProjectChange
from app.storage.services import pending_project_change_service

router = APIRouter(tags=["pending-project-changes"])


async def _to_response(
    session: AsyncSession,
    change: PendingProjectChange,
) -> PendingProjectChangeResponse:
    from app.storage.services import pending_project_change_apply_service

    applicability = await pending_project_change_apply_service.assess_pending_change(
        session, change
    )
    return PendingProjectChangeResponse.model_validate(change).model_copy(
        update={
            "is_applicable": applicability.is_applicable,
            "applicability_reason": applicability.reason,
        }
    )


@router.post(
    "/projects/{project_id}/pending-changes",
    response_model=PendingProjectChangeResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="创建待审项目变更",
)
async def create_pending_change(
    project_id: str,
    data: PendingProjectChangeCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PendingProjectChangeResponse:
    try:
        change = await pending_project_change_service.create_pending_change(
            session,
            project_id=project_id,
            target_type=data.target_type,
            target_id=data.target_id,
            operation=data.operation,
            after=data.after,
            source_task_id=data.source_task_id,
            source_message_id=data.source_message_id,
            model_id=data.model_id,
        )
        return await _to_response(session, change)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.get(
    "/projects/{project_id}/pending-changes",
    response_model=list[PendingProjectChangeResponse],
    summary="获取项目待审变更列表",
)
async def list_pending_changes(
    project_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    status: PendingProjectChangeStatus | None = None,
) -> list[PendingProjectChangeResponse]:
    try:
        changes = await pending_project_change_service.list_pending_changes(
            session, project_id, status
        )
        return [await _to_response(session, change) for change in changes]
    except NotFoundError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.post(
    "/projects/{project_id}/pending-changes/{change_id}/apply",
    response_model=PendingProjectChangeResponse,
    summary="采用待审项目变更",
)
async def apply_pending_change(
    project_id: str,
    change_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PendingProjectChangeResponse:
    from app.storage.services import pending_project_change_apply_service

    change = None
    try:
        change = await pending_project_change_service.get_pending_change(
            session, project_id, change_id
        )
        async with session.begin_nested():
            applied = await pending_project_change_apply_service.apply_pending_change(
                session, change
            )
        return await _to_response(session, applied)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except pending_project_change_apply_service.PendingChangeConflictError as exc:
        if change is not None:
            await session.refresh(change)
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail={
                "code": "pending_change_conflict",
                "message": str(exc),
                "current": exc.current,
                "current_hash": exc.current_hash,
            },
        ) from exc
    except ConflictError as exc:
        if change is not None:
            await session.refresh(change)
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ValidationError as exc:
        if change is not None:
            await session.refresh(change)
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.get(
    "/projects/{project_id}/pending-changes/count",
    summary="获取项目待审变更数量",
)
async def get_pending_change_count(
    project_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    status: PendingProjectChangeStatus = "pending",
) -> dict[str, int]:
    try:
        count = await pending_project_change_service.count_pending_changes(
            session, project_id, status
        )
        return {"count": count}
    except NotFoundError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.get(
    "/projects/{project_id}/pending-changes/{change_id}",
    response_model=PendingProjectChangeResponse,
    summary="获取待审项目变更详情",
)
async def get_pending_change(
    project_id: str,
    change_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PendingProjectChangeResponse:
    try:
        change = await pending_project_change_service.get_pending_change(
            session, project_id, change_id
        )
        return await _to_response(session, change)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.post(
    "/projects/{project_id}/pending-changes/{change_id}/reject",
    response_model=PendingProjectChangeResponse,
    summary="拒绝待审项目变更",
)
async def reject_pending_change(
    project_id: str,
    change_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PendingProjectChangeResponse:
    try:
        change = await pending_project_change_service.reject_pending_change(
            session, project_id, change_id
        )
        return await _to_response(session, change)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except ConflictError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
