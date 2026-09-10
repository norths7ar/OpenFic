"""
Model Router - 模型 API。
"""

import asyncio
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_settings_lock import require_agent_settings_unlocked
from app.api.schemas.model import (
    ModelCreateRequest,
    ModelResponse,
    ModelUpdateRequest,
    ModelValidationResponse,
    TaskType,
)
from app.core.encryption import EncryptionService
from app.core.errors import NotFoundError
from app.models.clients.reasoning_capabilities import (
    refresh_advertised_efforts,
    supported_reasoning_efforts,
)
from app.models.repos import model_provider_repo
from app.models.services import ModelService
from app.models.services.model_provider_service import ModelProviderService
from app.models.services.model_validation_service import ModelValidationService
from app.settings import settings
from app.storage.database import get_session

router = APIRouter(prefix="/models", tags=["models"])
_SUPPORTED_TASK_TYPES = frozenset({"llm", "embedding", "rerank"})


def get_model_service() -> ModelService:
    """获取模型服务实例。"""
    return ModelService()


def get_model_validation_service() -> ModelValidationService:
    return ModelValidationService(EncryptionService(settings.encryption_key))


def _require_task_type(task_type: str) -> TaskType:
    if task_type not in _SUPPORTED_TASK_TYPES:
        raise ValueError(f"Unsupported task_type: {task_type}")
    return cast(TaskType, task_type)


async def _warm_reasoning_capabilities(provider) -> None:
    if provider is None or provider.provider_type not in {
        "openai-compatible",
        "openai-compatible-responses",
    }:
        return
    try:
        service = ModelProviderService(EncryptionService(settings.encryption_key))
        await refresh_advertised_efforts(
            provider.provider_type,
            provider.url,
            service.get_decrypted_api_key(provider) or "",
            service.get_decrypted_custom_headers(provider),
        )
    except Exception:
        # Model listing must remain readable if saved credentials cannot decrypt.
        # Actual generation still validates credentials in model_resolution.
        return


async def _model_response(session: AsyncSession, model) -> ModelResponse:
    provider = await model_provider_repo.get_by_id(session, model.provider_id)
    await _warm_reasoning_capabilities(provider)
    return _to_response(model, provider)


def _to_response(m, provider=None) -> ModelResponse:
    return ModelResponse(
        id=m.id,
        name=m.name,
        remark=m.remark,
        provider_id=m.provider_id,
        model_id=m.model_id,
        task_type=_require_task_type(m.task_type),
        temperature=m.temperature,
        top_p=m.top_p,
        top_k=m.top_k,
        min_p=m.min_p,
        top_a=m.top_a,
        frequency_penalty=m.frequency_penalty,
        presence_penalty=m.presence_penalty,
        repetition_penalty=m.repetition_penalty,
        max_tokens=m.max_tokens,
        context_length=m.context_length,
        input_price=m.input_price,
        output_price=m.output_price,
        cache_read_price=m.cache_read_price,
        cache_write_price=m.cache_write_price,
        dimensions=m.dimensions,
        reasoning_effort_levels=list(
            supported_reasoning_efforts(provider.provider_type, m.model_id, provider.url)
        )
        if provider is not None and m.task_type == "llm"
        else [],
        is_builtin=m.is_builtin,
        is_enabled=m.is_enabled,
        created_at=m.created_at.isoformat(),
        updated_at=m.updated_at.isoformat(),
    )


@router.get(
    "",
    response_model=list[ModelResponse],
    summary="获取所有模型",
)
async def get_models(
    session: Annotated[AsyncSession, Depends(get_session)],
    service: Annotated[ModelService, Depends(get_model_service)],
    provider_id: str | None = None,
    task_type: str | None = None,
    include_disabled: bool = False,
) -> list[ModelResponse]:
    """
    获取所有模型或按条件过滤。

    Args:
        session: 数据库 session。
        service: 模型服务。
        provider_id: 可选的提供商 ID 过滤。
        task_type: 可选的任务类型过滤（llm 或 embedding）。

    Returns:
        模型列表。
    """
    if provider_id:
        models = await service.get_models_by_provider(
            session,
            provider_id,
            task_type,
            include_disabled=include_disabled,
        )
    else:
        all_models = await service.get_all_models(session, include_disabled=include_disabled)
        # 如果指定task_type，进行过滤
        if task_type:
            models = [m for m in all_models if m.task_type == task_type]
        else:
            models = all_models

    providers = {provider.id: provider for provider in await model_provider_repo.get_all(session)}
    used = {m.provider_id for m in models if m.task_type == "llm"}
    await asyncio.gather(
        *(
            _warm_reasoning_capabilities(provider)
            for key, provider in providers.items()
            if key in used
        )
    )
    return [_to_response(m, providers.get(m.provider_id)) for m in models]


@router.get(
    "/{model_id}",
    response_model=ModelResponse,
    summary="获取模型",
)
async def get_model(
    model_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    service: Annotated[ModelService, Depends(get_model_service)],
) -> ModelResponse:
    """
    根据 ID 获取模型。

    Args:
        model_id: 模型 ID。
        session: 数据库 session。
        service: 模型服务。

    Returns:
        模型信息。

    Raises:
        HTTPException: 如果模型不存在。
    """
    try:
        model = await service.get_model_by_id(session, model_id)
        return await _model_response(session, model)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post(
    "/{model_id}/validate",
    response_model=ModelValidationResponse,
    summary="验证已保存模型连接",
)
async def validate_model(
    model_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    service: Annotated[ModelService, Depends(get_model_service)],
    validation_service: Annotated[ModelValidationService, Depends(get_model_validation_service)],
) -> ModelValidationResponse:
    """Validate one saved provider/model pair without changing its configuration."""
    try:
        model = await service.get_model_by_id(session, model_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    provider = await model_provider_repo.get_by_id(session, model.provider_id)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider with id {model.provider_id} not found",
        )

    result = await validation_service.validate(model, provider)
    return ModelValidationResponse(
        success=result.success,
        message=result.message,
        error_code=result.error_code,
        detail=result.detail,
    )


@router.post(
    "",
    response_model=ModelResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建模型",
)
async def create_model(
    request: ModelCreateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    service: Annotated[ModelService, Depends(get_model_service)],
) -> ModelResponse:
    """
    创建模型。

    Args:
        request: 创建请求。
        session: 数据库 session。
        service: 模型服务。

    Returns:
        创建的模型信息。
    """
    await require_agent_settings_unlocked(session)
    logger.info(f"创建模型: {request.name}")

    try:
        model = await service.create_model(
            session=session,
            name=request.name,
            provider_id=request.provider_id,
            model_id=request.model_id,
            task_type=request.task_type,
            remark=request.remark,
            temperature=request.temperature,
            top_p=request.top_p,
            top_k=request.top_k,
            min_p=request.min_p,
            top_a=request.top_a,
            frequency_penalty=request.frequency_penalty,
            presence_penalty=request.presence_penalty,
            repetition_penalty=request.repetition_penalty,
            max_tokens=request.max_tokens,
            context_length=request.context_length,
            input_price=request.input_price,
            output_price=request.output_price,
            cache_read_price=request.cache_read_price,
            cache_write_price=request.cache_write_price,
            dimensions=request.dimensions,
            is_enabled=request.is_enabled,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    return await _model_response(session, model)


@router.put(
    "/{model_id}",
    response_model=ModelResponse,
    summary="更新模型",
)
async def update_model(
    model_id: str,
    request: ModelUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    service: Annotated[ModelService, Depends(get_model_service)],
) -> ModelResponse:
    """
    更新模型信息。

    Args:
        model_id: 模型 ID。
        request: 更新请求。
        session: 数据库 session。
        service: 模型服务。

    Returns:
        更新后的模型信息。

    Raises:
        HTTPException: 如果模型不存在。
    """
    await require_agent_settings_unlocked(session)
    logger.info(f"更新模型: {model_id}")

    try:
        model = await service.update_model(
            session=session,
            model_id=model_id,
            name=request.name,
            remark=request.remark,
            provider_id=request.provider_id,
            model_identifier=request.model_id,
            task_type=request.task_type,
            temperature=request.temperature,
            top_p=request.top_p,
            top_k=request.top_k,
            min_p=request.min_p,
            top_a=request.top_a,
            frequency_penalty=request.frequency_penalty,
            presence_penalty=request.presence_penalty,
            repetition_penalty=request.repetition_penalty,
            max_tokens=request.max_tokens,
            context_length=request.context_length,
            input_price=request.input_price,
            output_price=request.output_price,
            cache_read_price=request.cache_read_price,
            cache_write_price=request.cache_write_price,
            dimensions=request.dimensions,
            is_enabled=request.is_enabled,
        )

        return await _model_response(session, model)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.delete(
    "/{model_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除模型",
)
async def delete_model(
    model_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    service: Annotated[ModelService, Depends(get_model_service)],
) -> None:
    """
    删除模型。

    Args:
        model_id: 模型 ID。
        session: 数据库 session。
        service: 模型服务。

    Raises:
        HTTPException: 如果模型不存在。
    """
    await require_agent_settings_unlocked(session)
    logger.info(f"删除模型: {model_id}")

    try:
        await service.delete_model(session, model_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
