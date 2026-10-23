"""
Model Provider Service - 模型服务提供商业务逻辑层。

Service作为Executor，是唯一发起调用的地方，负责处理重试、熔断、fallback和观测。
"""

import asyncio
import json
from collections.abc import Mapping
from typing import Any

import httpx
from loguru import logger
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.encryption import EncryptionService
from app.core.errors import NotFoundError
from app.models.catalog import CatalogMatch, ModelProviderCatalogService
from app.models.clients.model_variants import visible_directory
from app.models.clients.provider_discovery import (
    DiscoverySnapshot,
    discover_provider_models,
    get_discovery_snapshot,
)
from app.models.entities.model_provider import ModelProvider
from app.models.registry import AdapterRegistry
from app.models.repos import model_provider_repo, model_repo
from app.models.services.model_lifecycle import release_model_references
from app.models.services.ocx_model_pairs import paired_records, require_unambiguous_pairs

_sync_locks: dict[str, asyncio.Lock] = {}

CUSTOM_PROVIDER_TYPES = frozenset(
    {
        "openai-compatible",
        "openai-compatible-responses",
        "anthropic-compatible",
    }
)


class ModelProviderService:
    """模型服务提供商Service（Executor），负责执行调用和观测。"""

    def __init__(
        self,
        encryption_service: EncryptionService,
        catalog_service: ModelProviderCatalogService | None = None,
    ):
        """
        初始化服务。

        Args:
            encryption_service: 加密服务实例。
        """
        self.encryption_service = encryption_service
        self.catalog_service = catalog_service or ModelProviderCatalogService()

    # ========================
    # CRUD 操作
    # ========================

    async def get_all_providers(self, session: AsyncSession) -> list[ModelProvider]:
        """
        获取所有提供商。

        Args:
            session: 数据库 session。

        Returns:
            提供商列表。
        """
        return await model_provider_repo.get_all(session)

    async def get_catalog_match(self, provider: ModelProvider) -> CatalogMatch | None:
        return await self.catalog_service.match_saved_provider(provider.provider_type, provider.url)

    async def get_supported_task_types(
        self,
        provider: ModelProvider,
        catalog_match: CatalogMatch | None = None,
    ) -> list[str]:
        if provider.is_builtin:
            return ["embedding", "rerank"]
        if catalog_match is None:
            catalog_match = await self.get_catalog_match(provider)
        return self.catalog_service.get_supported_task_types(
            provider.provider_type,
            catalog_match,
        )

    async def get_unavailable_task_types(
        self,
        provider: ModelProvider,
        catalog_match: CatalogMatch | None = None,
    ) -> list[str]:
        """List supported tasks whose native provider SDK is not installed."""
        task_types = await self.get_supported_task_types(provider, catalog_match)
        return [
            task_type
            for task_type in task_types
            if not AdapterRegistry.is_available(provider.provider_type, task_type)
        ]

    async def get_effective_icon_path(
        self,
        provider: ModelProvider,
        catalog_match: CatalogMatch | None = None,
    ) -> str | None:
        if catalog_match is None:
            catalog_match = await self.get_catalog_match(provider)
        return catalog_match.icon_path if catalog_match else None

    def get_decrypted_custom_headers(self, provider: ModelProvider) -> dict[str, str]:
        """获取自定义提供商的请求头，不向 API 响应暴露值。"""
        if provider.provider_type not in CUSTOM_PROVIDER_TYPES:
            return {}

        encrypted_headers = provider.custom_headers_encrypted
        if not encrypted_headers:
            return {}

        try:
            payload = json.loads(self.encryption_service.decrypt(encrypted_headers))
        except Exception:
            logger.warning("Failed to decrypt custom headers for provider {}", provider.id)
            return {}

        if not isinstance(payload, dict):
            return {}
        return {
            key: value
            for key, value in payload.items()
            if isinstance(key, str) and isinstance(value, str)
        }

    def get_custom_header_names(self, provider: ModelProvider) -> list[str]:
        """获取已配置的自定义请求头名称。"""
        return list(self.get_decrypted_custom_headers(provider))

    @staticmethod
    def _normalize_custom_headers(
        provider_type: str,
        entries: list[dict[str, str]] | None,
        existing_headers: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        """清理请求头输入，并在更新时保留未重新填写的旧值。"""
        existing = dict(existing_headers or {})
        normalized: dict[str, str] = {}

        for entry in entries or []:
            key = entry.get("key", "").strip()
            value = entry.get("value", "")
            if not isinstance(value, str):
                raise ValueError("自定义请求头值必须是字符串")
            if not key and not value:
                continue
            if "\r" in key or "\n" in key or "\r" in value or "\n" in value:
                raise ValueError("自定义请求头不能包含换行符")
            if not key:
                continue

            existing_key = next(
                (name for name in existing if name.casefold() == key.casefold()),
                None,
            )
            if not value and existing_key is not None:
                normalized[key] = existing[existing_key]
            elif value:
                normalized[key] = value

        if provider_type not in CUSTOM_PROVIDER_TYPES and normalized:
            raise ValueError("自定义请求头仅支持自定义类型提供商")
        return normalized

    async def get_provider_by_id(self, session: AsyncSession, provider_id: str) -> ModelProvider:
        """
        根据ID获取提供商。

        Args:
            session: 数据库session。
            provider_id: 提供商ID。

        Returns:
            提供商实例。

        Raises:
            NotFoundError: 如果提供商不存在。
        """
        provider = await model_provider_repo.get_by_id(session, provider_id)
        if not provider:
            raise NotFoundError(f"Provider with id {provider_id} not found")
        return provider

    async def create_provider(
        self,
        session: AsyncSession,
        name: str,
        url: str,
        api_key: str,
        provider_type: str,
        custom_headers: list[dict[str, str]] | None = None,
        catalog_mode: str = "generic",
    ) -> ModelProvider:
        """
        创建提供商。

        Args:
            session: 数据库 session。
            name: 提供商名称。
            url: 服务 URL。
            api_key: API Key（明文）。
            provider_type: 提供商类型。
            custom_headers: 自定义请求头。

        Returns:
            创建的提供商实例。
        """
        url = await self._resolve_provider_url(provider_type, url)

        # 加密 API Key
        encrypted_key = self.encryption_service.encrypt(api_key) if api_key else ""
        normalized_headers = self._normalize_custom_headers(provider_type, custom_headers)
        encrypted_headers = (
            self.encryption_service.encrypt(json.dumps(normalized_headers, ensure_ascii=False))
            if normalized_headers
            else ""
        )

        provider = await model_provider_repo.create(
            session=session,
            name=name,
            url=url,
            api_key_encrypted=encrypted_key,
            provider_type=provider_type,
            catalog_mode=catalog_mode,
            custom_headers_encrypted=encrypted_headers,
        )
        await session.commit()
        return provider

    async def _resolve_provider_url(self, provider_type: str, url: str) -> str:
        if provider_type in {
            "openai-compatible",
            "openai-compatible-responses",
            "anthropic-compatible",
        }:
            return url

        try:
            catalog_provider = await self.catalog_service.get_provider(provider_type)
        except KeyError:
            return url

        return catalog_provider.api or url

    async def update_provider(
        self,
        session: AsyncSession,
        provider_id: str,
        name: str | None = None,
        url: str | None = None,
        api_key: str | None = None,
        provider_type: str | None = None,
        catalog_mode: str | None = None,
        custom_headers: list[dict[str, str]] | None = None,
    ) -> ModelProvider:
        """
        更新提供商。

        Args:
            session: 数据库 session。
            provider_id: 提供商 ID。
            name: 提供商名称。
            url: 服务 URL。
            api_key: API Key（明文），如果提供则重新加密。
            provider_type: 提供商类型。
            custom_headers: 自定义请求头。

        Returns:
            更新后的提供商实例。

        Raises:
            NotFoundError: 如果提供商不存在。
        """
        existing = await model_provider_repo.get_by_id(session, provider_id)
        if existing is None:
            raise NotFoundError(f"Provider with id {provider_id} not found")
        if existing.is_builtin:
            raise ValueError("内置提供商不允许编辑")
        if catalog_mode == "ocx" and existing.catalog_mode != "ocx":
            saved = await model_repo.get_by_provider_id(session, provider_id, include_disabled=True)
            require_unambiguous_pairs(paired_records(saved))

        # 加密 API Key（如果提供）
        encrypted_key = None
        if api_key is not None:
            encrypted_key = self.encryption_service.encrypt(api_key) if api_key else ""

        effective_provider_type = provider_type or existing.provider_type
        encrypted_headers = None
        if custom_headers is not None:
            normalized_headers = self._normalize_custom_headers(
                effective_provider_type,
                custom_headers,
                self.get_decrypted_custom_headers(existing),
            )
            encrypted_headers = (
                self.encryption_service.encrypt(json.dumps(normalized_headers, ensure_ascii=False))
                if normalized_headers
                else ""
            )
        elif effective_provider_type not in CUSTOM_PROVIDER_TYPES:
            encrypted_headers = ""

        provider = await model_provider_repo.update(
            session=session,
            provider_id=provider_id,
            name=name,
            url=url,
            api_key_encrypted=encrypted_key,
            custom_headers_encrypted=encrypted_headers,
            provider_type=provider_type,
            catalog_mode=catalog_mode,
        )

        if not provider:
            raise NotFoundError(f"Provider with id {provider_id} not found")

        await session.commit()
        return provider

    async def delete_provider(self, session: AsyncSession, provider_id: str) -> None:
        """
        删除提供商。

        Args:
            session: 数据库 session。
            provider_id: 提供商 ID。

        Raises:
            NotFoundError: 如果提供商不存在。
            ValueError: 如果提供商为内置提供商，不允许删除。
        """
        provider = await model_provider_repo.get_by_id(session, provider_id)
        if provider is None:
            raise NotFoundError(f"Provider with id {provider_id} not found")
        if provider.is_builtin:
            raise ValueError("内置提供商不允许删除")
        models = await model_repo.get_by_provider_id(session, provider_id, include_disabled=True)
        for model in models:
            await release_model_references(session, model)
        success = await model_provider_repo.delete_by_id(session, provider_id)
        if not success:
            raise NotFoundError(f"Provider with id {provider_id} not found")
        await session.commit()

    async def sync_models(
        self,
        session: AsyncSession,
        provider_id: str,
        *,
        refresh: bool = False,
    ) -> dict[str, Any]:
        """Explicit LLM synchronization. Raw, complete directories alone authorize retirement."""
        async with _sync_locks.setdefault(provider_id, asyncio.Lock()):
            provider = await self.get_provider_by_id(session, provider_id)
            if provider.is_builtin:
                return dict(
                    success=True,
                    message="静态目录不执行清理",
                    models=[],
                    discovery_status="unsupported",
                )
            # Do not hold a read transaction over network IO. Keep an independent copy
            # because rollback expires ORM attributes.
            provider = ModelProvider.model_validate(provider.model_dump())
            signature = {
                key: getattr(provider, key)
                for key in (
                    "url",
                    "provider_type",
                    "api_key_encrypted",
                    "custom_headers_encrypted",
                    "catalog_mode",
                )
            }
            await session.rollback()
            try:
                api_key, headers = self.get_discovery_credentials(provider)
                snapshot = await discover_provider_models(
                    provider.provider_type,
                    provider.url,
                    api_key,
                    headers,
                    refresh=refresh,
                )
            except ValueError as exc:
                return dict(success=False, message=str(exc), models=[], discovery_status="error")
            result = dict(
                success=snapshot.status != "error",
                message=snapshot.error or "模型目录已同步",
                models=[],
                discovery_status=snapshot.status,
                discovery_checked_at=snapshot.checked_at,
                removed_models=[],
                affected_uses=[],
            )
            if snapshot.status != "error":
                result["models"] = await self.enrich_models_with_catalog_metadata(
                    provider,
                    "llm",
                    visible_directory(provider, snapshot, api_key, headers),
                )
            if snapshot.status != "ok":
                return result
            try:
                # Conditional write both verifies the connection and obtains a DB write
                # lock until commit; a concurrent connection edit cannot slip between
                # verification and deletion (including SQLite, where FOR UPDATE is ignored).
                claim = await session.execute(
                    update(ModelProvider)
                    .where(
                        col(ModelProvider.id) == provider_id,
                        *(getattr(ModelProvider, key) == value for key, value in signature.items()),
                    )
                    .values(catalog_mode=provider.catalog_mode)
                    .execution_options(synchronize_session=False)
                )
                if not getattr(claim, "rowcount", 0):
                    await session.rollback()
                    return dict(
                        success=False,
                        message="连接配置已变化，请重新同步",
                        models=[],
                        discovery_status="unknown",
                    )
                models = await model_repo.get_by_provider_id(
                    session, provider_id, include_disabled=True
                )
                raw_identifiers = {model.id: model.model_id for model in models}
                if provider.catalog_mode == "ocx":
                    groups = paired_records(models, snapshot.models)
                    try:
                        require_unambiguous_pairs(groups)
                    except ValueError as exc:
                        await session.rollback()
                        result.update(success=False, message=str(exc))
                        return result
                    for base, records in groups.items():
                        model = records[0]
                        if model.model_id == base + "--fast":
                            await model_repo.update(
                                session,
                                model.id,
                                model_identifier=base,
                                default_speed="fast",
                            )
                affected: list[str] = []
                removed: list[dict[str, str]] = []
                for model in models:
                    if (
                        model.task_type != "llm"
                        or model.is_builtin
                        or raw_identifiers[model.id] in snapshot.models
                    ):
                        continue
                    affected.extend(await release_model_references(session, model))
                    removed.append(dict(id=model.id, name=model.name, model_id=model.model_id))
                    await model_repo.delete_by_id(session, model.id)
                await session.commit()
                result["removed_models"] = removed
                result["affected_uses"] = list(dict.fromkeys(affected))
                return result
            except BaseException:
                await session.rollback()
                raise

    # ========================
    # API Key 操作
    # ========================

    def get_decrypted_api_key(self, provider: ModelProvider) -> str | None:
        """
        获取解密后的 API Key。

        Args:
            provider: 提供商实例。

        Returns:
            解密后的 API Key，如果加密字段为空或解密失败返回 None。
        """
        if not provider.api_key_encrypted or provider.api_key_encrypted.strip() == "":
            return None

        try:
            return self.encryption_service.decrypt(provider.api_key_encrypted)
        except Exception as e:
            logger.warning(f"Failed to decrypt API key for provider {provider.id}: {e}")
            return None

    # ========================
    # 模型列表获取（Executor执行点）
    # ========================

    async def validate_and_get_models(
        self,
        provider_type: str,
        url: str,
        api_key: str,
        custom_headers: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        """
        验证提供商连接并获取模型列表。

        Args:
            provider_type: 提供商类型。
            url: 服务 URL。
            api_key: API Key（明文）。
            custom_headers: 自定义请求头。

        Returns:
            模型列表，每个模型为 {"id": "model-id", "name": "Model Name"} 格式。

        Raises:
            Exception: 如果连接验证失败。
        """
        snapshot = await self.discover_connection(provider_type, url, api_key, custom_headers)
        return self._discovered_models(snapshot)

    async def discover_connection(
        self,
        provider_type: str,
        url: str,
        api_key: str,
        custom_headers: list[dict[str, str]] | None = None,
    ) -> DiscoverySnapshot:
        """Explicit connection validation shares discovery, but bypasses its TTL."""
        url = await self._resolve_provider_url(provider_type, url)
        request_headers = self._normalize_custom_headers(provider_type, custom_headers)
        return await discover_provider_models(
            provider_type, url, api_key, request_headers, refresh=True
        )

    def get_discovery_credentials(self, provider: ModelProvider) -> tuple[str, dict[str, str]]:
        """Do not query or reuse an anonymous snapshot when saved credentials are unreadable."""
        api_key = self.get_decrypted_api_key(provider) or ""
        if provider.api_key_encrypted and provider.api_key_encrypted.strip() and not api_key:
            raise ValueError("API Key 解密失败，请重新配置该提供商的 API Key")
        headers = self.get_decrypted_custom_headers(provider)
        if (
            provider.provider_type in CUSTOM_PROVIDER_TYPES
            and provider.custom_headers_encrypted
            and not headers
        ):
            raise ValueError("自定义请求头解密失败，请重新配置该提供商的请求头")
        return api_key, headers

    def get_llm_discovery_snapshot(self, provider: ModelProvider) -> DiscoverySnapshot:
        if provider.is_builtin:
            return DiscoverySnapshot(status="unsupported")
        api_key, headers = self.get_discovery_credentials(provider)
        return get_discovery_snapshot(provider.provider_type, provider.url, api_key, headers)

    @staticmethod
    def _discovered_models(snapshot: DiscoverySnapshot) -> list[dict[str, Any]]:
        if snapshot.status == "error":
            raise ValueError(snapshot.error or "获取模型目录失败")
        return list(snapshot.models.values())

    async def get_available_models(
        self, provider: ModelProvider, task_type: str, *, refresh: bool = False
    ) -> list[dict[str, Any]]:
        """
        获取指定provider和task_type的可用模型列表（Executor执行点）。

        Args:
            provider: 提供商实例。
            task_type: 任务类型（llm、embedding 或 rerank）。

        Returns:
            模型列表。

        Raises:
            ValueError: 如果不支持该provider和task_type组合。
            Exception: 如果请求失败。
        """
        if provider.is_builtin:
            return self._builtin_available_models(task_type)

        if task_type == "llm":
            api_key, headers = self.get_discovery_credentials(provider)
            snapshot = await discover_provider_models(
                provider.provider_type, provider.url, api_key, headers, refresh=refresh
            )
            self._discovered_models(snapshot)
            return visible_directory(provider, snapshot, api_key, headers)

        logger.info(
            f"Fetching available models for provider={provider.provider_type}, task_type={task_type}"
        )

        # 检查是否支持
        runtime_provider_type = (
            "anthropic-compatible"
            if provider.provider_type == "anthropic-compatible"
            else "openai-compatible-responses"
            if provider.provider_type == "openai-compatible-responses"
            else "openai-compatible"
        )
        if not AdapterRegistry.is_supported(runtime_provider_type, task_type):
            raise ValueError(
                f"Provider '{provider.provider_type}' does not support task_type '{task_type}'"
            )

        # 获取Adapter
        adapter = AdapterRegistry.get_adapter(runtime_provider_type)

        # 空密钥是无认证通用连接的合法配置，且不得尝试解密空字符串。
        api_key = self.get_decrypted_api_key(provider) or ""
        request_headers = self.get_decrypted_custom_headers(provider)

        # 创建HTTP客户端并执行请求
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # 根据task_type路由到对应方法
                if task_type == "rerank":
                    if request_headers:
                        models = await adapter.get_rerank_models(
                            client,
                            provider.url,
                            api_key,
                            headers=request_headers,
                        )
                    else:
                        models = await adapter.get_rerank_models(client, provider.url, api_key)
                else:
                    if request_headers:
                        models = await adapter.get_embedding_models(
                            client,
                            provider.url,
                            api_key,
                            headers=request_headers,
                        )
                    else:
                        models = await adapter.get_embedding_models(client, provider.url, api_key)

                logger.info(
                    f"Successfully fetched {len(models)} models for provider={provider.provider_type}, task_type={task_type}"
                )
                return models

        except Exception as e:
            logger.error(
                "Failed to fetch models for provider={}, task_type={}: {}",
                provider.provider_type,
                task_type,
                str(e),
                exc_info=True,
            )
            raise

    async def enrich_models_with_catalog_metadata(
        self,
        provider: ModelProvider,
        task_type: str,
        models: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """按 model id 将远端返回模型与 catalog 元数据对齐。"""

        enriched_models: list[dict[str, Any]] = [
            {
                **model,
                "id": model["id"],
                "name": model["name"],
                "task_type": task_type,
                "metadata": None,
            }
            for model in models
        ]

        if not models:
            return enriched_models

        catalog_match = await self.get_catalog_match(provider)
        if catalog_match is None:
            return enriched_models

        try:
            catalog_models = await self.catalog_service.get_provider_models(
                catalog_match.catalog_provider_type,
                task_type,
            )
        except KeyError:
            return enriched_models

        catalog_models_by_id = {model.model_id: model for model in catalog_models.models}

        for model in enriched_models:
            matched_model = catalog_models_by_id.get(model["id"])
            if matched_model is None:
                continue

            model["name"] = matched_model.display_name
            model["task_type"] = matched_model.task_type
            model["metadata"] = matched_model.metadata

        return self.catalog_service._sort_model_dicts_by_release_date(enriched_models)

    @staticmethod
    def _builtin_available_models(task_type: str) -> list[dict[str, str]]:
        """内置提供商的固定模型列表。"""
        from app.models.builtin import BUILTIN_MODELS

        return [
            {"id": spec.model_id, "name": spec.name}
            for spec in BUILTIN_MODELS
            if spec.task_type == task_type
        ]
