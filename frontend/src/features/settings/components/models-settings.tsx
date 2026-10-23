/**
 * Models Settings Component
 *
 * 模型设置面板，管理和配置 AI 模型。
 */

import { Badge, Box, Button, Flex, Link, Tabs, Text } from "@radix-ui/themes";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Edit } from "lucide-react";
import { useState, useCallback, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";

import { Spinner } from "@/components";
import {
  CapabilityIcon,
  ContextBadge,
  getModelCapabilityKeys,
  formatContextWindow,
} from "@/components/model-capability-tags";
import { ModelDiscoveryStatus } from "@/components/model-discovery-status";
import { ModelIdSelect, type ModelIdSelectOption } from "@/components/model-id-select";
import { toast } from "@/components/toast";
import { MODEL_DISCOVERY_QUERY_OPTIONS } from "@/lib/model-discovery";
import type { Model, ModelCreateRequest, ModelUpdateRequest } from "@/lib/model.types";

import {
  fetchModelProviderCatalogModels,
  fetchModels,
  fetchProviders,
  updateModel,
} from "../lib/model-api";
import {
  resolveProviderCatalogType,
  resolveProviderDisplayName,
  resolveProviderIconPath,
} from "../lib/provider-utils";
import { fetchSettings, updateSettings } from "../lib/settings-api";
import { DEFAULT_MODEL_SETTINGS_TAB, type ModelSettingsTab } from "../lib/settings-route";
import { useModelSync } from "../lib/use-model-sync";
import { AgentSettingsLockNotice } from "./agent-settings-lock-notice";
import { ModelFormDialog } from "./model-form-dialog";

import "./models-settings.css";

interface ModelsSettingsProps {
  activeTab?: ModelSettingsTab;
  onActiveTabChange?: (tab: ModelSettingsTab) => void;
  onManageProvider: (providerId: string) => void;
  isAgentSettingsLocked: boolean;
  isAgentSettingsLockLoading: boolean;
}

export function ModelsSettings({
  activeTab = DEFAULT_MODEL_SETTINGS_TAB,
  onActiveTabChange,
  isAgentSettingsLocked,
  isAgentSettingsLockLoading,
  onManageProvider,
}: ModelsSettingsProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const [formOpen, setFormOpen] = useState(false);
  const [editingModel, setEditingModel] = useState<Model | null>(null);

  useEffect(() => {
    if (!isAgentSettingsLocked) return;
    setFormOpen(false);
    setEditingModel(null);
  }, [isAgentSettingsLocked]);

  // 获取所有模型
  const { data: models, isLoading: isModelsLoading } = useQuery({
    ...MODEL_DISCOVERY_QUERY_OPTIONS,
    queryKey: ["models"],
    queryFn: () => fetchModels(),
  });

  // 获取所有提供商（用于显示提供商名称）
  const { data: providers, isLoading: isProvidersLoading } = useQuery({
    queryKey: ["model-providers"],
    queryFn: fetchProviders,
  });

  useModelSync(providers);

  // 获取设置
  const { data: settings, isLoading: isSettingsLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: fetchSettings,
  });

  // 更新设置
  const updateSettingsMutation = useMutation({
    mutationFn: updateSettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      toast.success(t("common.saveSuccess"));
    },
  });

  const handleDefaultModelChange = useCallback(
    (value: string) => {
      updateSettingsMutation.mutate({ default_model: value });
    },
    [updateSettingsMutation],
  );

  const handleLightModelChange = useCallback(
    (value: string) => {
      updateSettingsMutation.mutate({ light_model: value });
    },
    [updateSettingsMutation],
  );

  const llmModels = useMemo(
    () => models?.filter((m) => m.taskType === "llm" && m.isEnabled) ?? [],
    [models],
  );
  const llmCatalogProviderTypes = useMemo(() => {
    if (!providers || llmModels.length === 0) {
      return [];
    }

    return Array.from(
      new Set(
        llmModels
          .map((model) => providers.find((provider) => provider.id === model.providerId))
          .map((provider) => (provider ? resolveProviderCatalogType(provider) : null))
          .filter((providerType): providerType is string => Boolean(providerType)),
      ),
    );
  }, [llmModels, providers]);

  const { data: llmCatalogMetadata } = useQuery({
    queryKey: ["model-provider-catalog", "saved-llm-model-metadata", llmCatalogProviderTypes],
    queryFn: async () => {
      const responses = await Promise.all(
        llmCatalogProviderTypes.map(async (providerType) => {
          const result = await fetchModelProviderCatalogModels(providerType, "llm");
          return [providerType, result.models] as const;
        }),
      );

      return new Map(responses);
    },
    enabled: llmCatalogProviderTypes.length > 0,
  });

  const llmModelOptions: ModelIdSelectOption[] = useMemo(() => {
    return llmModels.map((model) => {
      const provider = providers?.find((entry) => entry.id === model.providerId);
      const catalogProviderType = provider ? resolveProviderCatalogType(provider) : null;
      const providerIconPath = provider ? resolveProviderIconPath(provider) : null;
      const catalogModel = catalogProviderType
        ? llmCatalogMetadata?.get(catalogProviderType)?.find((entry) => entry.id === model.modelId)
        : null;

      return {
        value: model.id,
        id: model.modelId,
        name: model.name,
        taskType: "llm",
        releaseDate: catalogModel?.releaseDate ?? null,
        reasoning: catalogModel?.reasoning ?? null,
        toolCall: catalogModel?.toolCall ?? null,
        inputModalities: catalogModel?.inputModalities ?? [],
        limit: catalogModel?.limit ?? null,
        cost: catalogModel?.cost ?? null,
        contextWindow: catalogModel?.contextWindow ?? model.contextLength,
        inputPricePerMillion:
          catalogModel?.inputPricePerMillion ?? (model.inputPrice > 0 ? model.inputPrice : null),
        outputPricePerMillion:
          catalogModel?.outputPricePerMillion ?? (model.outputPrice > 0 ? model.outputPrice : null),
        cacheReadPricePerMillion:
          catalogModel?.cacheReadPricePerMillion ??
          (model.cacheReadPrice > 0 ? model.cacheReadPrice : null),
        cacheWritePricePerMillion:
          catalogModel?.cacheWritePricePerMillion ??
          (model.cacheWritePrice > 0 ? model.cacheWritePrice : null),
        source: catalogModel?.source ?? "catalog",
        providerIconPath,
        upstreamStatus: model.upstreamStatus,
        discoveryStatus: model.discoveryStatus,
        discoveryCheckedAt: model.discoveryCheckedAt,
      };
    });
  }, [llmCatalogMetadata, llmModels, providers]);

  const llmModelMetadataMap = useMemo(() => {
    const map = new Map<string, ModelIdSelectOption>();
    for (const option of llmModelOptions) {
      map.set(option.value ?? option.id, option);
    }
    return map;
  }, [llmModelOptions]);

  // 更新模型
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: ModelUpdateRequest }) => updateModel(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["models"] });
      setFormOpen(false);
      setEditingModel(null);
      toast.success(t("models.updateSuccess"));
    },
    onError: () => {
      toast.error(t("models.updateFailed"));
    },
  });

  // 打开编辑对话框
  const handleEdit = useCallback((model: Model) => {
    setEditingModel({ ...model });
    setFormOpen(true);
  }, []);

  // 提交表单
  const handleSubmit = useCallback(
    async (data: ModelCreateRequest | ModelUpdateRequest) => {
      if (editingModel) {
        await updateMutation.mutateAsync({
          id: editingModel.id,
          data: data as ModelUpdateRequest,
        });
      }
    },
    [editingModel, updateMutation],
  );

  // 获取提供商名称
  const getProviderName = useCallback(
    (providerId: string) => {
      const provider = providers?.find((p) => p.id === providerId);
      if (!provider) return providerId;
      return provider.name || resolveProviderDisplayName(provider);
    },
    [providers],
  );

  const filteredModels = models?.filter((m) => m.taskType === activeTab && m.isEnabled) || [];
  const isContentLoading =
    isModelsLoading || isProvidersLoading || isSettingsLoading || isAgentSettingsLockLoading;

  const handleActiveTabChange = useCallback(
    (value: string) => {
      onActiveTabChange?.(value as ModelSettingsTab);
    },
    [onActiveTabChange],
  );

  if (isContentLoading) {
    return (
      <Flex
        align="center"
        justify="center"
        style={{ height: "100%" }}
      >
        <Spinner size={18} />
      </Flex>
    );
  }

  return (
    <Box>
      <AgentSettingsLockNotice isLocked={isAgentSettingsLocked} />
      <Flex
        direction="column"
        gap="4"
      >
        {/* 描述 */}
        <Text
          size="2"
          color="gray"
        >
          {t("models.description")}
        </Text>
        <Text
          size="1"
          color="gray"
        >
          {t("models.autoRefreshModels")}
        </Text>

        {/* 默认模型 & 轻量模型 */}
        <Flex
          direction="column"
          gap="4"
        >
          <Flex
            direction="column"
            gap="1"
            style={{ maxWidth: 400, minWidth: 0 }}
          >
            <Text
              size="2"
              weight="medium"
            >
              {t("models.defaultModel")}
            </Text>
            <Text
              size="1"
              color="gray"
              style={{ marginBottom: "var(--space-1)" }}
            >
              {t("models.defaultModelDesc")}
            </Text>
            <ModelIdSelect
              value={settings?.defaultModel || ""}
              onChange={handleDefaultModelChange}
              models={llmModelOptions}
              placeholder={t("models.chooseEachTime")}
              editable={false}
              allowCustomValue={false}
              disabled={isAgentSettingsLocked}
              emptyOptionLabel={t("models.chooseEachTime")}
            />
          </Flex>

          <Flex
            direction="column"
            gap="1"
            style={{ maxWidth: 400, minWidth: 0 }}
          >
            <Text
              size="2"
              weight="medium"
            >
              {t("models.lightModel")}
            </Text>
            <Text
              size="1"
              color="gray"
              style={{ marginBottom: "var(--space-1)" }}
            >
              {t("models.lightModelDesc")}
            </Text>
            <ModelIdSelect
              value={settings?.lightModel || ""}
              onChange={handleLightModelChange}
              models={llmModelOptions}
              placeholder={t("models.followDefault")}
              editable={false}
              allowCustomValue={false}
              disabled={isAgentSettingsLocked}
              emptyOptionLabel={t("models.followDefault")}
            />
          </Flex>
        </Flex>

        {/* Tab导航 */}
        <Tabs.Root
          value={activeTab}
          onValueChange={handleActiveTabChange}
        >
          <Tabs.List>
            <Tabs.Trigger value="llm">{t("models.llmModels")}</Tabs.Trigger>
            <Tabs.Trigger value="embedding">{t("models.embeddingModels")}</Tabs.Trigger>
            <Tabs.Trigger value="rerank">{t("models.rerankModels")}</Tabs.Trigger>
          </Tabs.List>
        </Tabs.Root>

        {/* 模型列表 */}
        {filteredModels.length > 0 ? (
          <Flex direction="column">
            {filteredModels.map((model, index) => (
              <Box
                key={model.id}
                className="list-item-hover"
              >
                <Flex
                  direction="column"
                  gap="3"
                  style={{ padding: "var(--space-4)" }}
                >
                  <Flex
                    align="center"
                    justify="between"
                    gap="3"
                  >
                    <Flex
                      direction="column"
                      gap="1"
                      className="models-settings-model-info"
                    >
                      {/* 模型名称 + 元数据标签 */}
                      <Flex
                        align="center"
                        gap="2"
                        wrap="wrap"
                      >
                        <Text
                          size="3"
                          weight="medium"
                        >
                          {model.name}
                        </Text>
                        <ModelDiscoveryStatus model={model} />
                        {model.isBuiltin ? (
                          <Badge
                            size="1"
                            color="green"
                            variant="soft"
                          >
                            {t("models.builtin")}
                          </Badge>
                        ) : null}
                        {(() => {
                          const metadata = llmModelMetadataMap.get(model.id);
                          if (!metadata) return null;
                          const capabilityKeys = getModelCapabilityKeys(metadata);
                          const contextLabel = formatContextWindow(metadata.contextWindow);
                          if (capabilityKeys.length === 0 && !contextLabel) return null;
                          return (
                            <Flex
                              align="center"
                              gap="1"
                            >
                              {capabilityKeys.map((cap) => (
                                <CapabilityIcon
                                  key={cap}
                                  capability={cap}
                                />
                              ))}
                              {contextLabel ? <ContextBadge label={contextLabel} /> : null}
                            </Flex>
                          );
                        })()}
                      </Flex>

                      {/* 提供商和模型 ID */}
                      <Flex
                        align="center"
                        gap="2"
                        wrap="wrap"
                      >
                        {model.isBuiltin ? (
                          <Text
                            size="2"
                            color="gray"
                          >
                            {getProviderName(model.providerId)}
                          </Text>
                        ) : (
                          <Link
                            asChild
                            size="2"
                            color="gray"
                            underline="hover"
                          >
                            <button
                              type="button"
                              className="models-settings-provider-link"
                              title={t("models.manageThisProvider")}
                              onClick={() => onManageProvider(model.providerId)}
                            >
                              {getProviderName(model.providerId)}
                            </button>
                          </Link>
                        )}
                        <Text
                          size="2"
                          color="gray"
                        >
                          •
                        </Text>
                        <Text
                          size="2"
                          color="gray"
                        >
                          {model.modelId}
                        </Text>
                      </Flex>

                      {/* 备注 */}
                      {model.remark && (
                        <Text
                          size="2"
                          color="gray"
                        >
                          {model.remark}
                        </Text>
                      )}
                    </Flex>

                    {/* 操作按钮 */}
                    <Flex flexShrink="0">
                      {model.isBuiltin ? null : (
                        <Button
                          size="2"
                          variant="soft"
                          color="gray"
                          onClick={() => handleEdit(model)}
                          aria-label={t("models.editModel")}
                          disabled={isAgentSettingsLocked}
                        >
                          <Edit size={14} />
                          {t("common.edit")}
                        </Button>
                      )}
                    </Flex>
                  </Flex>
                </Flex>
                {index < filteredModels.length - 1 && (
                  <Box
                    style={{
                      height: "1px",
                      background: "var(--gray-a4)",
                      marginLeft: "var(--space-4)",
                      marginRight: "var(--space-4)",
                    }}
                  />
                )}
              </Box>
            ))}
          </Flex>
        ) : (
          <Flex
            direction="column"
            align="center"
            justify="center"
            gap="3"
            style={{ height: 200 }}
          >
            <Text
              size="2"
              color="gray"
            >
              {t("models.noModels")}
            </Text>
          </Flex>
        )}
      </Flex>

      {/* 表单对话框 */}
      <ModelFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        model={editingModel || undefined}
        models={models ?? []}
        onSubmit={handleSubmit}
        parametersOnly
        isSubmitting={updateMutation.isPending}
        isAgentSettingsLocked={isAgentSettingsLocked}
      />
    </Box>
  );
}
