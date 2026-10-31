import type { ReasoningEffort } from "./agent.types";

/**
 * Model and Provider Types
 *
 * 模型和提供商相关类型定义。
 */

/** 提供商类型，目录提供商标识由 models.dev 动态提供。 */
export type ProviderType = string;

/** 任务类型 */
export type TaskType = "llm" | "embedding" | "rerank";

export type ReasoningEffortStatus = "supported" | "unsupported" | "unknown";
export type ModelSpeed = "standard" | "fast";
export type ProviderCatalogMode = "generic" | "ocx";

export interface SpeedReasoningCapability {
  levels: ReasoningEffort[];
  status: ReasoningEffortStatus;
  default: ReasoningEffort | null;
}

export interface ModelSpeedFields {
  defaultSpeed?: ModelSpeed;
  speedVariants?: Partial<Record<ModelSpeed, string>>;
  speedReasoningCapabilities?: Partial<Record<ModelSpeed, SpeedReasoningCapability>>;
}

export type ModelDiscoveryStatus = "ok" | "error" | "unsupported" | "unknown";
export type UpstreamModelStatus = "listed" | "not_listed" | "unknown";

export interface ModelDiscoveryFields {
  upstreamStatus?: UpstreamModelStatus;
  discoveryStatus?: ModelDiscoveryStatus;
  discoveryCheckedAt?: string | null;
}

/** 模型服务提供商 */
export interface ModelProvider {
  hasApiKey: boolean;
  id: string;
  name: string;
  url: string;
  providerType: ProviderType;
  catalogMode?: ProviderCatalogMode;
  customHeaderNames: string[];
  supportedTaskTypes: TaskType[];
  unavailableTaskTypes: TaskType[];
  iconPath: string | null;
  isBuiltin: boolean;
  catalogMatch: ModelProviderCatalogMatch | null;
  createdAt: string;
  updatedAt: string;
}

export type CatalogMatchSource = "provider_type" | "api";

export interface ModelProviderCatalogMatch {
  catalogProviderType: string;
  displayName: string;
  defaultUrl: string | null;
  api: string | null;
  iconPath: string | null;
  modelsDevProviderId: string | null;
  matchedVia: CatalogMatchSource;
}

/** 模型服务提供商响应（后端格式） */
export type ModelProviderResponse = import("@/api/generated/models").ModelProviderResponse;

/** 创建/更新提供商请求 (FormData) */
export type ModelProviderFormData = FormData;

/** 验证提供商请求 */
export interface ModelProviderValidateRequest {
  provider_type: string;
  url: string;
  api_key: string;
  custom_headers?: ModelProviderCustomHeader[];
}

export interface ModelProviderCustomHeader {
  key: string;
  value: string;
}

/** 可用模型 */
export interface AvailableModel extends ModelDiscoveryFields, ModelSpeedFields {
  reasoningEffortLevels?: ReasoningEffort[];
  reasoningEffortStatus?: ReasoningEffortStatus;
  reasoningEffortDefault?: ReasoningEffort | null;
  id: string;
  name: string;
  taskType?: TaskType | null;
  releaseDate?: string | null;
  reasoning?: boolean | null;
  toolCall?: boolean | null;
  inputModalities?: string[];
  limit?: Record<string, unknown> | string | number | null;
  cost?: Record<string, unknown> | string | number | null;
  contextWindow?: number | null;
  inputPricePerMillion?: number | null;
  outputPricePerMillion?: number | null;
  cacheReadPricePerMillion?: number | null;
  cacheWritePricePerMillion?: number | null;
  source?: "catalog" | "remote";
}

/** 验证提供商响应 */
export interface ModelProviderValidateResponse {
  discoveryStatus?: ModelDiscoveryStatus;
  discoveryCheckedAt?: string | null;
  success: boolean;
  message: string;
  models: AvailableModel[];
}

export interface ModelProviderSyncResponse extends ModelProviderValidateResponse {
  removedModels: { id: string; name: string; modelId: string }[];
  affectedUses: string[];
}

export type ModelValidationErrorCode =
  | "authentication_failed"
  | "connection_failed"
  | "model_not_found"
  | "protocol_incompatible"
  | "capability_incompatible"
  | "rate_limited"
  | "timed_out"
  | "unknown_error";

export type ModelValidationResponse = import("@/api/generated/models").ModelValidationResponse;

/** 模型 */
export interface Model extends ModelDiscoveryFields, ModelSpeedFields {
  reasoningEffortLevels?: ReasoningEffort[];
  reasoningEffortStatus?: ReasoningEffortStatus;
  reasoningEffortDefault?: ReasoningEffort | null;
  id: string;
  name: string;
  remark: string;
  providerId: string;
  modelId: string;
  taskType: TaskType;
  temperature: number | null;
  topP: number | null;
  topK: number | null;
  minP: number | null;
  topA: number | null;
  frequencyPenalty: number | null;
  presencePenalty: number | null;
  repetitionPenalty: number | null;
  maxTokens: number | null;
  contextLength: number;
  inputPrice: number;
  outputPrice: number;
  cacheReadPrice: number;
  cacheWritePrice: number;
  dimensions: number | null;
  isBuiltin: boolean;
  isEnabled: boolean;
  createdAt: string;
  updatedAt: string;
}

/** 模型响应（后端格式） */
export type ModelResponse = import("@/api/generated/models").ModelResponse;

/** 创建模型请求 */
export type ModelCreateRequest = import("@/api/generated/models").ModelCreateRequest;

/** 更新模型请求 */
export type ModelUpdateRequest = import("@/api/generated/models").ModelUpdateRequest;

export interface ModelProviderCatalogProvider {
  providerType: string;
  displayName: string;
  defaultUrl: string | null;
  api: string | null;
  iconPath: string | null;
  modelsDevProviderId: string | null;
  supportedTaskTypes: TaskType[];
  modelCounts: Partial<Record<TaskType, number>>;
}

export interface ModelProviderCatalogModel extends AvailableModel {
  taskType: TaskType;
}

export interface ModelProviderCatalogModelsResponse {
  provider: ModelProviderCatalogProvider;
  models: ModelProviderCatalogModel[];
}
