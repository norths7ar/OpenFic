import type * as schemas from "@/api/generated/models";
import * as http from "@/api/generated/openfic";
/**
 * Model API
 *
 * 模型和提供商 API 客户端。
 */
import type {
  AvailableModel,
  Model,
  ModelCreateRequest,
  ModelProviderCatalogMatch,
  ModelProviderCatalogModelsResponse,
  ModelProviderCatalogProvider,
  ModelProvider,
  ModelProviderResponse,
  ModelProviderValidateRequest,
  ModelProviderValidateResponse,
  ModelProviderCatalogModel,
  ModelResponse,
  ModelValidationResponse,
  TaskType,
  ModelUpdateRequest,
  ModelProviderSyncResponse,
} from "@/lib/model.types";

type ModelProviderCatalogProviderResponse = schemas.CatalogProviderSummary;

type ModelProviderCatalogModelResponse = schemas.CatalogProviderModelSummary;

type ModelProviderAvailableModelApiResponse = schemas.AvailableModel;

function readNumericMetadataField(value: unknown, key: string): number | null {
  if (value === null || value === undefined) {
    return null;
  }

  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }

  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  if (typeof value !== "object" || !(key in value)) return null;
  const entry = (value as Record<string, unknown>)[key];
  if (typeof entry === "number") {
    return Number.isFinite(entry) ? entry : null;
  }
  if (typeof entry === "string") {
    const parsed = Number(entry);
    return Number.isFinite(parsed) ? parsed : null;
  }

  return null;
}

function transformCatalogMatch(
  raw: NonNullable<ModelProviderResponse["catalog_match"]> | null | undefined,
): ModelProviderCatalogMatch | null {
  if (!raw) {
    return null;
  }

  return {
    catalogProviderType: raw.catalog_provider_type,
    displayName: raw.display_name,
    defaultUrl: raw.default_url ?? null,
    api: raw.api ?? null,
    iconPath: raw.icon_path ?? null,
    modelsDevProviderId: raw.models_dev_provider_id ?? null,
    matchedVia: raw.matched_via,
  };
}

/**
 * 后端响应字段转换（snake_case -> camelCase）- Provider
 */
function transformProvider(raw: ModelProviderResponse): ModelProvider {
  return {
    id: raw.id,
    name: raw.name,
    url: raw.url,
    hasApiKey: raw.has_api_key,
    providerType: raw.provider_type as ModelProvider["providerType"],
    catalogMode: raw.catalog_mode ?? "generic",
    customHeaderNames: raw.custom_header_names ?? [],
    supportedTaskTypes: raw.supported_task_types as ModelProvider["supportedTaskTypes"],
    unavailableTaskTypes: (raw.unavailable_task_types ??
      []) as ModelProvider["unavailableTaskTypes"],
    iconPath: raw.icon_path || null,
    isBuiltin: raw.is_builtin ?? false,
    catalogMatch: transformCatalogMatch(raw.catalog_match),
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

/**
 * 后端响应字段转换（snake_case -> camelCase）- Model
 */
function transformModel(raw: ModelResponse): Model {
  return {
    defaultSpeed: raw.default_speed ?? "standard",
    speedVariants: raw.speed_variants,
    speedReasoningCapabilities: raw.speed_reasoning_capabilities,
    upstreamStatus: raw.upstream_status ?? "unknown",
    discoveryStatus: raw.discovery_status ?? "unknown",
    discoveryCheckedAt: raw.discovery_checked_at,
    id: raw.id,
    name: raw.name,
    remark: raw.remark,
    providerId: raw.provider_id,
    modelId: raw.model_id,
    taskType: raw.task_type,
    temperature: raw.temperature,
    topP: raw.top_p,
    topK: raw.top_k,
    minP: raw.min_p,
    topA: raw.top_a,
    frequencyPenalty: raw.frequency_penalty,
    presencePenalty: raw.presence_penalty,
    repetitionPenalty: raw.repetition_penalty,
    maxTokens: raw.max_tokens,
    contextLength: raw.context_length ?? 0,
    inputPrice: raw.input_price ?? 0,
    outputPrice: raw.output_price ?? 0,
    cacheReadPrice: raw.cache_read_price ?? 0,
    cacheWritePrice: raw.cache_write_price ?? 0,
    dimensions: raw.dimensions,
    isBuiltin: raw.is_builtin ?? false,
    isEnabled: raw.is_enabled ?? true,
    reasoningEffortLevels: raw.reasoning_effort_levels ?? [],
    reasoningEffortStatus: raw.reasoning_effort_status ?? "unknown",
    reasoningEffortDefault: raw.reasoning_effort_default,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

function transformCatalogProvider(
  raw: ModelProviderCatalogProviderResponse,
): ModelProviderCatalogProvider {
  return {
    providerType: raw.provider_type,
    displayName: raw.display_name,
    defaultUrl: raw.default_url ?? null,
    api: raw.api ?? null,
    iconPath: raw.icon_path ?? null,
    modelsDevProviderId: raw.models_dev_provider_id ?? null,
    supportedTaskTypes:
      raw.supported_task_types as ModelProviderCatalogProvider["supportedTaskTypes"],
    modelCounts: raw.model_counts ?? {},
  };
}

function transformCatalogModel(raw: ModelProviderCatalogModelResponse): ModelProviderCatalogModel {
  const metadata = raw.metadata ?? null;
  const modalities = metadata?.modalities;
  const inputs =
    modalities && typeof modalities === "object" && "input" in modalities
      ? modalities.input
      : undefined;
  const numericMetadata = (value: unknown): Record<string, unknown> | string | number | null => {
    if (typeof value === "string" || typeof value === "number") return value;
    return value && typeof value === "object" && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : null;
  };

  return {
    id: raw.model_id,
    name: raw.display_name,
    taskType: raw.task_type,
    releaseDate: typeof metadata?.release_date === "string" ? metadata.release_date : null,
    reasoning: typeof metadata?.reasoning === "boolean" ? metadata.reasoning : null,
    toolCall: typeof metadata?.tool_call === "boolean" ? metadata.tool_call : null,
    inputModalities: Array.isArray(inputs)
      ? inputs.filter((item): item is string => typeof item === "string")
      : [],
    limit: numericMetadata(metadata?.limit),
    cost: numericMetadata(metadata?.cost),
    contextWindow: readNumericMetadataField(metadata?.limit, "context"),
    inputPricePerMillion: readNumericMetadataField(metadata?.cost, "input"),
    outputPricePerMillion: readNumericMetadataField(metadata?.cost, "output"),
    cacheReadPricePerMillion: readNumericMetadataField(metadata?.cost, "cache_read"),
    cacheWritePricePerMillion: readNumericMetadataField(metadata?.cost, "cache_write"),
    source: "catalog",
  };
}

function transformAvailableModel(
  raw: ModelProviderAvailableModelApiResponse,
  source: "catalog" | "remote",
): AvailableModel {
  const metadata = raw.metadata ?? null;

  return {
    defaultSpeed: "standard",
    speedVariants: raw.speed_variants,
    speedReasoningCapabilities: raw.speed_reasoning_capabilities,
    id: raw.id,
    name: raw.name,
    taskType: raw.task_type ?? null,
    releaseDate: metadata?.release_date ?? null,
    reasoning: metadata?.reasoning ?? null,
    toolCall: metadata?.tool_call ?? null,
    inputModalities: metadata?.modalities?.input ?? [],
    limit: metadata?.limit ?? null,
    cost: metadata?.cost ?? null,
    contextWindow: readNumericMetadataField(metadata?.limit, "context"),
    inputPricePerMillion: readNumericMetadataField(metadata?.cost, "input"),
    outputPricePerMillion: readNumericMetadataField(metadata?.cost, "output"),
    cacheReadPricePerMillion: readNumericMetadataField(metadata?.cost, "cache_read"),
    cacheWritePricePerMillion: readNumericMetadataField(metadata?.cost, "cache_write"),
    source,
  };
}

// ========== Provider APIs ==========

/**
 * 获取所有提供商
 */
export async function fetchProviders(): Promise<ModelProvider[]> {
  const response = await http.getProvidersApiV1ModelProvidersGet();
  return response.data.map(transformProvider);
}

/**
 * 根据 ID 获取提供商
 */
export async function fetchProvider(id: string): Promise<ModelProvider> {
  const response = await http.getProviderApiV1ModelProvidersProviderIdGet(id);
  return transformProvider(response.data);
}

/**
 * 创建提供商
 */
export async function createProvider(data: FormData): Promise<ModelProvider> {
  const response = await http.createProviderApiV1ModelProvidersPost(data, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return transformProvider(response.data);
}

/**
 * 更新提供商
 */
export async function updateProvider(id: string, data: FormData): Promise<ModelProvider> {
  const response = await http.updateProviderApiV1ModelProvidersProviderIdPut(id, data, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return transformProvider(response.data);
}

/**
 * 删除提供商
 */
export async function deleteProvider(id: string): Promise<void> {
  await http.deleteProviderApiV1ModelProvidersProviderIdDelete(id);
}

/**
 * 验证提供商连接
 */
export async function validateProvider(
  data: ModelProviderValidateRequest,
): Promise<ModelProviderValidateResponse> {
  const response = await http.validateProviderApiV1ModelProvidersValidatePost(data);
  return {
    ...response.data,
    models: (response.data.models || []).map((model) => transformAvailableModel(model, "remote")),
  };
}

/**
 * 获取提供商的模型列表
 */
export async function fetchProviderModels(
  providerId: string,
  taskType: TaskType = "llm",
  refresh = false,
): Promise<ModelProviderValidateResponse> {
  const response = await http.getProviderModelsApiV1ModelProvidersProviderIdModelsGet(providerId, {
    task_type: taskType,
    refresh,
  });
  return {
    ...response.data,
    discoveryStatus: response.data.discovery_status ?? "unknown",
    discoveryCheckedAt: response.data.discovery_checked_at,
    models: (response.data.models || []).map((model) => transformAvailableModel(model, "remote")),
  };
}

/** Explicit reconciliation; GET directory endpoints never remove saved models. */
export async function syncProviderModels(
  providerId: string,
  refresh = false,
): Promise<ModelProviderSyncResponse> {
  const response = await http.syncProviderModelsApiV1ModelProvidersProviderIdModelsSyncPost(
    providerId,
    { refresh },
  );
  const raw = response.data;
  return {
    success: raw.success,
    message: raw.message,
    discoveryStatus: raw.discovery_status ?? "unknown",
    discoveryCheckedAt: raw.discovery_checked_at,
    models: (raw.models ?? []).map((model) => transformAvailableModel(model, "remote")),
    removedModels: (raw.removed_models ?? []).map((model) => ({
      id: model.id,
      name: model.name,
      modelId: model.model_id,
    })),
    affectedUses: raw.affected_uses ?? [],
  };
}

export async function fetchModelUsage(id: string): Promise<string[]> {
  const response = await http.getModelUsageApiV1ModelsModelIdUsageGet(id);
  return response.data.uses;
}

export async function fetchModelProviderCatalogProviders(): Promise<
  ModelProviderCatalogProvider[]
> {
  const response = await http.listCatalogProvidersApiV1ModelProviderCatalogProvidersGet();
  return response.data.map(transformCatalogProvider);
}

export async function fetchModelProviderCatalogModels(
  providerType: string,
  taskType: TaskType,
): Promise<ModelProviderCatalogModelsResponse> {
  const response =
    await http.getCatalogProviderModelsApiV1ModelProviderCatalogProvidersProviderTypeModelsGet(
      providerType,
      { task_type: taskType },
    );

  return {
    provider: transformCatalogProvider(response.data.provider),
    models: (response.data.models || []).map(transformCatalogModel),
  };
}

// ========== Model APIs ==========

/**
 * 获取所有模型
 */
export async function fetchModels(
  providerId?: string,
  taskType?: string,
  includeDisabled = false,
): Promise<Model[]> {
  const params: Record<string, string> = {};
  if (providerId) params.provider_id = providerId;
  if (taskType) params.task_type = taskType;
  if (includeDisabled) params.include_disabled = "true";
  const response = await http.getModelsApiV1ModelsGet(params);
  return response.data.map(transformModel);
}

/**
 * 根据 ID 获取模型
 */
export async function fetchModel(id: string): Promise<Model> {
  const response = await http.getModelApiV1ModelsModelIdGet(id);
  return transformModel(response.data);
}

/** Validate one saved provider/model pair without mutating its configuration. */
export async function validateModel(id: string): Promise<ModelValidationResponse> {
  const response = await http.validateModelApiV1ModelsModelIdValidatePost(id);
  return response.data;
}

/**
 * 创建模型
 */
export async function createModel(data: ModelCreateRequest): Promise<Model> {
  const response = await http.createModelApiV1ModelsPost(data);
  return transformModel(response.data);
}

/**
 * 更新模型
 */
export async function updateModel(id: string, data: ModelUpdateRequest): Promise<Model> {
  const response = await http.updateModelApiV1ModelsModelIdPut(id, data);
  return transformModel(response.data);
}

/**
 * 删除模型
 */
export async function deleteModel(id: string): Promise<void> {
  await http.deleteModelApiV1ModelsModelIdDelete(id);
}
