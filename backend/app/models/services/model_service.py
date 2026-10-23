"""
Model Service - 模型业务逻辑层。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.clients.model_params import (
    DEFAULT_CONTEXT_LENGTH,
    DEFAULT_FREQUENCY_PENALTY,
    DEFAULT_MIN_P,
    DEFAULT_PRESENCE_PENALTY,
    DEFAULT_REPETITION_PENALTY,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_A,
    DEFAULT_TOP_K,
    DEFAULT_TOP_P,
    with_default,
)
from app.models.entities.model import Model
from app.models.repos import model_repo
from app.models.services.model_lifecycle import model_uses, release_model_references
from app.storage.repos import retrieval_index_repo


class ModelService:
    """模型 Service。"""

    async def _normalize_variant(
        self,
        session: AsyncSession,
        provider_id: str,
        raw_id: str,
        default_speed: str | None,
        *,
        exclude_id: str | None = None,
    ) -> tuple[str, str | None]:
        from app.core.encryption import EncryptionService
        from app.models.repos import model_provider_repo
        from app.models.services.model_provider_service import ModelProviderService
        from app.settings import settings

        provider = await model_provider_repo.get_by_id(session, provider_id)
        if provider is None:
            raise NotFoundError(f"Provider with id {provider_id} not found")
        if provider.catalog_mode != "ocx":
            return raw_id, default_speed
        service = ModelProviderService(EncryptionService(settings.encryption_key))
        # Read the authenticated live snapshot, not a guessed suffix relationship.
        try:
            await service.get_available_models(provider, "llm")
        except ValueError:
            pass
        try:
            snapshot = service.get_llm_discovery_snapshot(provider)
        except ValueError:
            return raw_id, default_speed
        base_id = raw_id.removesuffix("--fast") if raw_id.endswith("--fast") else raw_id
        if (
            snapshot.checked_at is None
            or base_id not in snapshot.models
            or base_id + "--fast" not in snapshot.models
        ):
            return raw_id, default_speed
        for existing in await model_repo.get_by_provider_id(
            session, provider_id, include_disabled=True
        ):
            if (
                existing.id != exclude_id
                and existing.task_type == "llm"
                and existing.model_id in {base_id, base_id + "--fast"}
            ):
                raise ValueError("该 OCX 模型已有共享配置，请编辑现有模型，不要重复添加速度变体")
        return base_id, "fast" if raw_id != base_id else default_speed

    async def get_all_models(
        self, session: AsyncSession, *, include_disabled: bool = False
    ) -> list[Model]:
        """
        获取所有模型。

        Args:
            session: 数据库 session。

        Returns:
            模型列表。
        """
        return await model_repo.get_all(session, include_disabled=include_disabled)

    async def get_models_by_provider(
        self,
        session: AsyncSession,
        provider_id: str,
        task_type: str | None = None,
        *,
        include_disabled: bool = False,
    ) -> list[Model]:
        """
        根据提供商 ID 获取模型列表，可选按task_type过滤。

        Args:
            session: 数据库 session。
            provider_id: 提供商 ID。
            task_type: 可选的任务类型过滤（llm、embedding 或 rerank）。

        Returns:
            模型列表。
        """
        models = await model_repo.get_by_provider_id(
            session, provider_id, include_disabled=include_disabled
        )
        if task_type:
            models = [m for m in models if m.task_type == task_type]
        return models

    async def get_model_by_id(self, session: AsyncSession, model_id: str) -> Model:
        """
        根据 ID 获取模型。

        Args:
            session: 数据库 session。
            model_id: 模型 ID。

        Returns:
            模型实例。

        Raises:
            NotFoundError: 如果模型不存在。
        """
        model = await model_repo.get_by_id(session, model_id)
        if not model:
            raise NotFoundError(f"Model with id {model_id} not found")
        return model

    async def create_model(
        self,
        session: AsyncSession,
        name: str,
        provider_id: str,
        model_id: str,
        task_type: str = "llm",
        remark: str = "",
        temperature: float | None = DEFAULT_TEMPERATURE,
        top_p: float | None = DEFAULT_TOP_P,
        top_k: int | None = DEFAULT_TOP_K,
        min_p: float | None = DEFAULT_MIN_P,
        top_a: float | None = DEFAULT_TOP_A,
        frequency_penalty: float | None = DEFAULT_FREQUENCY_PENALTY,
        presence_penalty: float | None = DEFAULT_PRESENCE_PENALTY,
        repetition_penalty: float | None = DEFAULT_REPETITION_PENALTY,
        max_tokens: int | None = None,
        context_length: int = DEFAULT_CONTEXT_LENGTH,
        input_price: float = 0.0,
        output_price: float = 0.0,
        cache_read_price: float = 0.0,
        cache_write_price: float = 0.0,
        dimensions: int | None = None,
        is_enabled: bool = True,
        default_speed: str = "standard",
    ) -> Model:
        """
        创建模型。

        Args:
            session: 数据库 session。
            name: 模型名称。
            provider_id: 关联的提供商 ID。
            model_id: 从提供商获取的模型 ID。
            task_type: 任务类型（llm、embedding 或 rerank）。
            remark: 备注。
            temperature: Temperature 参数（LLM）。
            top_p: Top P 参数（LLM）。
            top_k: Top K 参数（LLM）。
            min_p: Min P 参数（LLM）。
            top_a: Top A 参数（LLM）。
            frequency_penalty: Frequency Penalty 参数（LLM）。
            presence_penalty: Presence Penalty 参数（LLM）。
            repetition_penalty: Repetition Penalty 参数（LLM）。
            max_tokens: Max Tokens 参数（LLM）。
            dimensions: Embedding 维度（Embedding）。
        Returns:
            创建的模型实例。
        """
        if task_type == "llm":
            model_id, normalized_speed = await self._normalize_variant(
                session,
                provider_id,
                model_id,
                default_speed,
            )
            default_speed = normalized_speed or "standard"
        if await model_repo.exists_by_name(session, name):
            raise ValueError("模型名称已存在")

        if task_type != "llm":
            temperature = None
            top_p = None
            top_k = None
            min_p = None
            top_a = None
            frequency_penalty = None
            presence_penalty = None
            repetition_penalty = None
        else:
            temperature = with_default(temperature, DEFAULT_TEMPERATURE)
            top_p = with_default(top_p, DEFAULT_TOP_P)
            top_k = with_default(top_k, DEFAULT_TOP_K)
            min_p = with_default(min_p, DEFAULT_MIN_P)
            top_a = with_default(top_a, DEFAULT_TOP_A)
            frequency_penalty = with_default(frequency_penalty, DEFAULT_FREQUENCY_PENALTY)
            presence_penalty = with_default(presence_penalty, DEFAULT_PRESENCE_PENALTY)
            repetition_penalty = with_default(repetition_penalty, DEFAULT_REPETITION_PENALTY)

        model = await model_repo.create(
            session=session,
            name=name,
            provider_id=provider_id,
            model_id=model_id,
            task_type=task_type,
            remark=remark,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            min_p=min_p,
            top_a=top_a,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            repetition_penalty=repetition_penalty,
            max_tokens=max_tokens,
            context_length=context_length,
            input_price=input_price,
            output_price=output_price,
            cache_read_price=cache_read_price,
            cache_write_price=cache_write_price,
            dimensions=dimensions,
            is_enabled=is_enabled,
            default_speed=default_speed,
        )
        await session.commit()
        return model

    async def update_model(
        self,
        session: AsyncSession,
        model_id: str,
        name: str | None = None,
        remark: str | None = None,
        provider_id: str | None = None,
        model_identifier: str | None = None,
        task_type: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        min_p: float | None = None,
        top_a: float | None = None,
        frequency_penalty: float | None = None,
        presence_penalty: float | None = None,
        repetition_penalty: float | None = None,
        max_tokens: int | None = None,
        context_length: int | None = None,
        input_price: float | None = None,
        output_price: float | None = None,
        cache_read_price: float | None = None,
        cache_write_price: float | None = None,
        dimensions: int | None = None,
        is_enabled: bool | None = None,
        default_speed: str | None = None,
    ) -> Model:
        """
        更新模型。

        Args:
            session: 数据库 session。
            model_id: 模型 ID。
            name: 模型名称。
            remark: 备注。
            provider_id: 关联的提供商 ID。
            model_identifier: 从提供商获取的模型 ID。
            task_type: 任务类型。
            temperature: Temperature 参数。
            top_p: Top P 参数。
            top_k: Top K 参数。
            min_p: Min P 参数。
            top_a: Top A 参数。
            frequency_penalty: Frequency Penalty 参数。
            presence_penalty: Presence Penalty 参数。
            repetition_penalty: Repetition Penalty 参数。
            max_tokens: Max Tokens 参数。
            dimensions: Embedding 维度。
        Returns:
            更新后的模型实例。

        Raises:
            NotFoundError: 如果模型不存在。
        """
        existing = await self.get_model_by_id(session, model_id)
        if existing.is_builtin:
            raise ValueError("内置模型不允许编辑")
        if (task_type or existing.task_type) == "llm":
            model_identifier, default_speed = await self._normalize_variant(
                session,
                provider_id or existing.provider_id,
                model_identifier or existing.model_id,
                default_speed,
                exclude_id=existing.id,
            )
        if is_enabled is False and existing.is_enabled:
            if existing.task_type == "llm":
                await release_model_references(session, existing)
            else:
                usage_labels = await self._get_model_usage_labels(session, model_id)
                if usage_labels:
                    raise ValueError("模型正在被以下配置使用，不能停用：" + "、".join(usage_labels))
        if name is not None and await model_repo.exists_by_name(
            session, name, exclude_model_id=model_id
        ):
            raise ValueError("模型名称已存在")
        if await retrieval_index_repo.exists_by_embedding_model_ref_id(session, model_id):
            protected_changes = []
            if provider_id is not None and provider_id != existing.provider_id:
                protected_changes.append("provider_id")
            if model_identifier is not None and model_identifier != existing.model_id:
                protected_changes.append("model_id")
            if dimensions is not None and dimensions != existing.dimensions:
                protected_changes.append("dimensions")
            if protected_changes:
                raise ValueError(
                    "Embedding model is bound to retrieval indexes; cannot change "
                    + ", ".join(protected_changes)
                )

        model = await model_repo.update(
            session=session,
            model_id=model_id,
            name=name,
            remark=remark,
            provider_id=provider_id,
            model_identifier=model_identifier,
            task_type=task_type,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            min_p=min_p,
            top_a=top_a,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            repetition_penalty=repetition_penalty,
            max_tokens=max_tokens,
            context_length=context_length,
            input_price=input_price,
            output_price=output_price,
            cache_read_price=cache_read_price,
            cache_write_price=cache_write_price,
            dimensions=dimensions,
            is_enabled=is_enabled,
            default_speed=default_speed,
        )

        if not model:
            raise NotFoundError(f"Model with id {model_id} not found")

        await session.commit()
        return model

    async def _get_model_usage_labels(self, session: AsyncSession, model_id: str) -> list[str]:
        return await model_uses(session, model_id)

    async def delete_model(self, session: AsyncSession, model_id: str) -> None:
        """
        删除模型。

        Args:
            session: 数据库 session。
            model_id: 模型 ID。

        Raises:
            NotFoundError: 如果模型不存在。
            ValueError: 如果模型为内置模型，不允许删除。
        """
        model = await model_repo.get_by_id(session, model_id)
        if not model:
            raise NotFoundError(f"Model with id {model_id} not found")
        if model.is_builtin:
            raise ValueError("内置模型不允许删除")
        await release_model_references(session, model)
        success = await model_repo.delete_by_id(session, model_id)
        if not success:
            raise NotFoundError(f"Model with id {model_id} not found")
        await session.commit()
