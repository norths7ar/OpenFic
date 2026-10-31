"""
ModelProvider API Schemas - 模型服务提供商请求/响应模型。
"""

from typing import Annotated, Any, Literal

from pydantic import Field, WithJsonSchema

from app.api.schemas.base import APIModel


class CatalogMatchResponse(APIModel):
    """Matched catalog provider metadata for a saved provider."""

    catalog_provider_type: str = Field(description="匹配到的 catalog provider_type")
    display_name: str = Field(description="Catalog 提供商显示名")
    default_url: str | None = Field(default=None, description="Catalog 默认 URL")
    api: str | None = Field(default=None, description="Models.dev api 字段")
    icon_path: str | None = Field(default=None, description="内置图标路径")
    models_dev_provider_id: str | None = Field(default=None, description="Models.dev provider id")
    matched_via: Annotated[
        str, WithJsonSchema({"type": "string", "enum": ["provider_type", "api"]})
    ] = Field(description="provider_type 或 api")


class ModelProviderResponse(APIModel):
    """提供商响应。"""

    id: str = Field(description="提供商 ID")
    name: str = Field(description="提供商名称/备注")
    url: str = Field(description="服务 URL")
    provider_type: str = Field(description="提供商类型")
    catalog_mode: Literal["generic", "ocx"] = "generic"
    has_api_key: bool = Field(description="Whether an API key is configured; never its value")
    custom_header_names: list[str] = Field(
        default_factory=list,
        description="已配置的自定义请求头名称（不返回请求头值）",
    )
    supported_task_types: list[str] = Field(
        description="支持的任务类型列表 (llm, embedding, rerank)"
    )
    unavailable_task_types: list[str] = Field(
        default_factory=list,
        description="当前未安装可选 SDK 的任务类型",
    )
    icon_path: str | None = Field(description="Catalog 图标路径")
    is_builtin: bool = Field(default=False, description="是否为内置提供商")
    catalog_match: CatalogMatchResponse | None = Field(
        default=None, description="匹配到的 catalog 提供商元数据"
    )
    created_at: str = Field(description="创建时间")
    updated_at: str = Field(description="更新时间")


class CustomHeaderEntry(APIModel):
    """单条自定义请求头。"""

    key: str = Field(description="请求头名称")
    value: str = Field(description="请求头值")


class ModelProviderValidateRequest(APIModel):
    """验证提供商连接请求。"""

    provider_type: str = Field(description="提供商类型")
    url: str = Field(description="服务 URL")
    api_key: str = Field(default="", description="API Key；无认证通用连接可留空")
    custom_headers: list[CustomHeaderEntry] = Field(
        default_factory=list,
        description="自定义请求头",
    )


class AvailableModelMetadata(APIModel):
    """模型展示元数据。"""

    release_date: str | None = Field(default=None, description="模型发布日期")
    reasoning: bool | None = Field(default=None, description="是否支持 reasoning")
    tool_call: bool | None = Field(default=None, description="是否支持 tool call")
    modalities: dict[str, list[str]] | None = Field(default=None, description="输入输出模态")
    limit: dict[str, Any] | str | int | None = Field(default=None, description="上下文与输出限制")
    cost: dict[str, Any] | str | int | None = Field(default=None, description="价格元数据")


class AvailableModel(APIModel):
    """可用模型。"""

    id: str = Field(description="模型 ID")
    name: str = Field(description="模型名称")
    speed_variants: dict[str, str] = Field(default_factory=dict, exclude_if=lambda value: not value)
    speed_reasoning_capabilities: dict[str, dict[str, Any]] = Field(
        default_factory=dict, exclude_if=lambda value: not value
    )
    task_type: (
        Annotated[str, WithJsonSchema({"type": "string", "enum": ["llm", "embedding", "rerank"]})]
        | None
    ) = Field(default=None, description="任务类型")
    metadata: AvailableModelMetadata | None = Field(
        default=None, description="匹配到的 catalog 元数据"
    )


class ModelProviderValidateResponse(APIModel):
    """验证提供商连接响应。"""

    success: bool = Field(description="是否验证成功")
    message: str = Field(description="消息")
    models: list[AvailableModel] = Field(description="可用模型列表")
    discovery_status: Literal["ok", "error", "unsupported", "unknown"] = "unknown"
    discovery_checked_at: str | None = Field(
        default=None, description="最后一次成功查询真实上游目录的 UTC ISO 时间"
    )


class RemovedModel(APIModel):
    id: str
    name: str
    model_id: str


class ModelProviderSyncResponse(ModelProviderValidateResponse):
    removed_models: list[RemovedModel] = Field(default_factory=list)
    affected_uses: list[str] = Field(default_factory=list)
