"""HTTP boundary for application settings."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings_service
from app.api.schemas.setting import (
    AgentSettingsLockResponse,
    AuditDetailsStorageResponse,
    ClearAuditDetailsResponse,
    SettingsResponse,
    SettingsUpdateRequest,
)
from app.storage.database import get_session

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get(
    "/agent-session-lock",
    response_model=AgentSettingsLockResponse,
    summary="获取 Agent 会话设置锁定状态",
)
async def get_agent_settings_lock(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AgentSettingsLockResponse:
    return await settings_service.get_agent_settings_lock(session)


@router.get(
    "",
    response_model=SettingsResponse,
    summary="获取设置",
)
async def get_settings(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SettingsResponse:
    return await settings_service.get_settings(session)


@router.put(
    "",
    response_model=SettingsResponse,
    status_code=status.HTTP_200_OK,
    summary="更新设置",
)
@router.patch(
    "",
    response_model=SettingsResponse,
    status_code=status.HTTP_200_OK,
    summary="更新设置",
)
async def update_settings(
    request: SettingsUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SettingsResponse:
    return await settings_service.update_settings(request, session)


@router.get(
    "/audit-details/storage",
    response_model=AuditDetailsStorageResponse,
    summary="获取 LLM 调用详情存储概览",
)
async def get_audit_details_storage(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuditDetailsStorageResponse:
    return await settings_service.get_audit_details_storage(session)


@router.delete(
    "/audit-details",
    response_model=ClearAuditDetailsResponse,
    summary="清空 LLM 调用详情",
)
async def clear_audit_details(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ClearAuditDetailsResponse:
    return await settings_service.clear_audit_details(session)
