import "./model-form-dialog.css";
import { zodResolver } from "@hookform/resolvers/zod";
import { Box, Dialog, Flex, Button, Text, TextField, TextArea, Separator } from "@radix-ui/themes";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo } from "react";
import { useForm, Controller, useWatch } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { z } from "zod";

import { Spinner } from "@/components";
import { ModelIdSelect } from "@/components/model-id-select";
import { LabeledSelect } from "@/components/select";
import type {
  Model,
  ModelCreateRequest,
  ModelProvider,
  ModelUpdateRequest,
  TaskType,
} from "@/lib/model.types";

import { fetchProviders } from "../lib/model-api";
import {
  isSelectableModelProvider,
  isCustomProviderType,
  resolveProviderCatalogType,
  resolveProviderDisplayName,
  supportsEmbeddingDimensions,
} from "../lib/provider-utils";
import { useProviderModelsQuery } from "../lib/use-provider-models-query";
import { AdvancedParamsSection } from "./advanced-params-section";
import { ModelMetadataSection } from "./model-metadata-section";

// 先定义 schema 和类型，以便在 ModelParamField 中使用
const modelSchema = z.object({
  name: z.string().min(1, "nameRequired"),
  taskType: z.enum(["llm", "embedding", "rerank"]),
  providerId: z.string().min(1, "providerRequired"),
  modelId: z.string().min(1, "modelIdRequired"),
  defaultSpeed: z.enum(["standard", "fast"]),
  remark: z.string().optional(),
  temperature: z.number().min(0).max(2),
  topP: z.number().min(0).max(1),
  topK: z.number().int().min(0).max(128),
  minP: z.number().min(0).max(1),
  topA: z.number().min(0).max(1),
  frequencyPenalty: z.number().min(-2).max(2),
  presencePenalty: z.number().min(-2).max(2),
  repetitionPenalty: z.number().min(0).max(2),
  maxTokens: z.number().min(1).nullable().optional(),
  contextLength: z.number().int().min(0).max(2000000),
  inputPrice: z.number().min(0),
  outputPrice: z.number().min(0),
  cacheReadPrice: z.number().min(0),
  cacheWritePrice: z.number().min(0),
  dimensions: z.number().min(1).max(4096).nullable().optional(),
});

type ModelFormData = z.infer<typeof modelSchema>;

interface ModelFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  model?: Model;
  models: Model[];
  onSubmit: (data: ModelCreateRequest | ModelUpdateRequest) => Promise<void>;
  isSubmitting: boolean;
  isAgentSettingsLocked: boolean;
  fixedProviderId?: string;
  initialTaskType?: TaskType;
  parametersOnly?: boolean;
}

export function ModelFormDialog({
  open,
  onOpenChange,
  model,
  models,
  onSubmit,
  isSubmitting,
  isAgentSettingsLocked,
  fixedProviderId,
  initialTaskType = "llm",
  parametersOnly = false,
}: ModelFormDialogProps) {
  const { t } = useTranslation();
  const isEditing = !!model;

  const {
    control,
    handleSubmit,
    formState: { errors },
    getValues,
    setValue,
    reset,
  } = useForm<ModelFormData>({
    resolver: zodResolver(modelSchema),
    defaultValues: {
      name: "",
      taskType: "llm" as TaskType,
      providerId: "",
      modelId: "",
      defaultSpeed: "standard",
      remark: "",
      temperature: 1,
      topP: 1,
      topK: 0,
      minP: 0,
      topA: 0,
      frequencyPenalty: 0,
      presencePenalty: 0,
      repetitionPenalty: 1,
      maxTokens: null,
      contextLength: 0,
      inputPrice: 0,
      outputPrice: 0,
      cacheReadPrice: 0,
      cacheWritePrice: 0,
      dimensions: null,
    },
  });

  // 当对话框打开或模型改变时，重置表单值
  useEffect(() => {
    if (open) {
      if (model) {
        // 编辑模式：回填所有值
        reset({
          name: model.name || "",
          taskType: (model.taskType as TaskType) || "llm",
          providerId: model.providerId || "",
          modelId: model.modelId || "",
          defaultSpeed: model.defaultSpeed ?? "standard",
          remark: model.remark || "",
          temperature: model.temperature ?? 1,
          topP: model.topP ?? 1,
          topK: model.topK ?? 0,
          minP: model.minP ?? 0,
          topA: model.topA ?? 0,
          frequencyPenalty: model.frequencyPenalty ?? 0,
          presencePenalty: model.presencePenalty ?? 0,
          repetitionPenalty: model.repetitionPenalty ?? 1,
          maxTokens: model.maxTokens ?? null,
          contextLength: model.contextLength ?? 0,
          inputPrice: model.inputPrice ?? 0,
          outputPrice: model.outputPrice ?? 0,
          cacheReadPrice: model.cacheReadPrice ?? 0,
          cacheWritePrice: model.cacheWritePrice ?? 0,
          dimensions: model.dimensions ?? null,
        });
      } else {
        // 新建模式：重置为空
        reset({
          name: "",
          taskType: initialTaskType,
          providerId: fixedProviderId ?? "",
          modelId: "",
          defaultSpeed: "standard",
          remark: "",
          temperature: 1,
          topP: 1,
          topK: 0,
          minP: 0,
          topA: 0,
          frequencyPenalty: 0,
          presencePenalty: 0,
          repetitionPenalty: 1,
          maxTokens: null,
          contextLength: 0,
          inputPrice: 0,
          outputPrice: 0,
          cacheReadPrice: 0,
          cacheWritePrice: 0,
          dimensions: null,
        });
      }
    } else {
      reset();
    }
  }, [open, model, reset, fixedProviderId, initialTaskType]);

  const providerId = useWatch({ control, name: "providerId" });
  const taskType = useWatch({ control, name: "taskType" });
  const name = useWatch({ control, name: "name" });
  const selectedModelId = useWatch({ control, name: "modelId" });
  const defaultSpeed = useWatch({ control, name: "defaultSpeed" });
  const hasDuplicateName = models.some((entry) => entry.id !== model?.id && entry.name === name);
  // 获取提供商列表
  const { data: providers } = useQuery({
    queryKey: ["model-providers"],
    queryFn: fetchProviders,
    staleTime: 5 * 60 * 1000,
  });

  // 模型目录可能缺少实际支持的任务类型，因此只排除内置提供商。
  const filteredProviders = useMemo(() => {
    if (!providers) return [];
    return providers.filter(isSelectableModelProvider);
  }, [providers]);

  const selectedProvider = useMemo(
    () => providers?.find((p) => p.id === providerId),
    [providers, providerId],
  );
  const selectedCatalogProviderType = useMemo(
    () => (selectedProvider ? resolveProviderCatalogType(selectedProvider) : null),
    [selectedProvider],
  );
  const selectedProviderSupportsEmbeddingDimensions = useMemo(
    () => (selectedProvider ? supportsEmbeddingDimensions(selectedProvider.providerType) : false),
    [selectedProvider],
  );
  const isModelSelectionDisabled = !providerId;

  const getProviderOptionLabel = useCallback((provider: ModelProvider) => {
    return provider.name || provider.url || resolveProviderDisplayName(provider);
  }, []);

  // Query keys isolate provider/task responses; polling never writes form values.
  const remoteQuery = useProviderModelsQuery(
    providerId,
    taskType,
    open && Boolean(selectedProvider),
  );
  const availableModels = useMemo(() => remoteQuery.data?.models ?? [], [remoteQuery.data?.models]);
  const loadingModels = remoteQuery.isLoading;
  const speedVariants =
    availableModels.find((entry) => entry.id === selectedModelId)?.speedVariants ??
    model?.speedVariants;
  const speedUnavailable = defaultSpeed === "fast" && !speedVariants?.fast;
  const modelsError = remoteQuery.isError
    ? remoteQuery.error?.message || t("models.fetchModelsFailed")
    : remoteQuery.data?.discoveryStatus === "error"
      ? t("models.discoveryFailed")
      : "";

  // 仅在创建表单没有提供商时清空模型选择。
  // 编辑表单的 reset() 会在 watch 值同步前触发，不能据此清空已保存的模型 ID。
  useEffect(() => {
    if (!providerId && !isEditing) {
      queueMicrotask(() => {
        setValue("modelId", "");
      });
    }
  }, [isEditing, providerId, setValue]);

  const handleProviderChange = useCallback(
    (nextProviderId: string) => {
      setValue("providerId", nextProviderId);
      setValue("modelId", "");
    },
    [setValue],
  );

  const handleTaskTypeChange = useCallback(
    (nextTaskType: string) => {
      setValue("taskType", nextTaskType as TaskType);
      setValue("modelId", "");
    },
    [setValue],
  );

  useEffect(() => {
    if (taskType !== "embedding" || !selectedProviderSupportsEmbeddingDimensions) {
      setValue("dimensions", null);
    }
  }, [selectedProviderSupportsEmbeddingDimensions, setValue, taskType]);

  // 处理模型ID选择
  const handleModelIdChange = useCallback(
    (modelId: string, modelName?: string) => {
      setValue("modelId", modelId);
      if (modelName && !getValues("name")) {
        setValue("name", modelName);
      }
      const catalogModel = availableModels.find((entry) => entry.id === modelId);
      if (
        catalogModel &&
        (catalogModel.source === "catalog" ||
          catalogModel.contextWindow !== null ||
          catalogModel.cost !== null) &&
        typeof catalogModel.contextWindow === "number" &&
        catalogModel.contextWindow >= 0 &&
        catalogModel.contextWindow <= 2000000
      ) {
        setValue("contextLength", catalogModel.contextWindow);
      }
      setValue("inputPrice", catalogModel?.inputPricePerMillion ?? getValues("inputPrice"));
      setValue("outputPrice", catalogModel?.outputPricePerMillion ?? getValues("outputPrice"));
      setValue(
        "cacheReadPrice",
        catalogModel?.cacheReadPricePerMillion ?? getValues("cacheReadPrice"),
      );
      setValue(
        "cacheWritePrice",
        catalogModel?.cacheWritePricePerMillion ?? getValues("cacheWritePrice"),
      );
    },
    [availableModels, getValues, setValue],
  );

  // 提交表单
  const onFormSubmit = useCallback(
    async (data: ModelFormData) => {
      // LLM模型的高级参数必须有实际值（使用默认值替代null）
      const requestData = {
        name: data.name,
        task_type: data.taskType,
        provider_id: data.providerId,
        model_id: data.modelId,
        default_speed: data.defaultSpeed,
        remark: data.remark || "",
        temperature: data.taskType === "llm" ? data.temperature : null,
        top_p: data.taskType === "llm" ? data.topP : null,
        top_k: data.taskType === "llm" ? data.topK : null,
        min_p: data.taskType === "llm" ? data.minP : null,
        top_a: data.taskType === "llm" ? data.topA : null,
        frequency_penalty: data.taskType === "llm" ? data.frequencyPenalty : null,
        presence_penalty: data.taskType === "llm" ? data.presencePenalty : null,
        repetition_penalty: data.taskType === "llm" ? data.repetitionPenalty : null,
        max_tokens: data.taskType === "llm" ? data.maxTokens : null,
        context_length: data.taskType === "llm" ? data.contextLength : 0,
        input_price: data.taskType === "llm" ? data.inputPrice : 0,
        output_price: data.taskType === "llm" ? data.outputPrice : 0,
        cache_read_price: data.taskType === "llm" ? data.cacheReadPrice : 0,
        cache_write_price: data.taskType === "llm" ? data.cacheWritePrice : 0,
        dimensions:
          data.taskType === "embedding" && selectedProviderSupportsEmbeddingDimensions
            ? data.dimensions
            : null,
      };

      try {
        await onSubmit(requestData);
        reset();
      } catch (error) {
        console.error("提交失败:", error);
        throw error;
      }
    },
    [onSubmit, reset, selectedProviderSupportsEmbeddingDimensions],
  );

  const handleOpenChange = useCallback(
    (newOpen: boolean) => {
      if (!newOpen) {
        reset();
      }
      onOpenChange(newOpen);
    },
    [onOpenChange, reset],
  );

  return (
    <Dialog.Root
      open={open}
      onOpenChange={handleOpenChange}
    >
      <Dialog.Content
        maxWidth="600px"
        className="model-form-dialog__content"
      >
        <Dialog.Title>{isEditing ? t("models.editModel") : t("models.createModel")}</Dialog.Title>
        {!isEditing && fixedProviderId && taskType === "llm" ? (
          <Dialog.Description size="1">{t("models.manualAddSyncHint")}</Dialog.Description>
        ) : null}

        <Box className="hide-scrollbar model-form-dialog__fields">
          <form
            onSubmit={handleSubmit(onFormSubmit, (errors) => {
              console.error("表单验证错误:", errors);
            })}
          >
            <Flex
              direction="column"
              gap="4"
              mt="4"
            >
              {/* 模型名称 */}
              <Flex
                direction="column"
                gap="2"
              >
                <Text
                  size="2"
                  weight="medium"
                  color="gray"
                >
                  {t("models.name")}{" "}
                  <Text
                    color="red"
                    className="model-form-dialog__required-mark"
                  >
                    *
                  </Text>
                </Text>
                <Controller
                  name="name"
                  control={control}
                  render={({ field }) => (
                    <TextField.Root
                      {...field}
                      placeholder={t("models.namePlaceholder")}
                      disabled={isAgentSettingsLocked}
                      color={hasDuplicateName ? "red" : undefined}
                    />
                  )}
                />
                {hasDuplicateName && (
                  <Text
                    size="1"
                    color="red"
                  >
                    {t("models.nameDuplicate")}
                  </Text>
                )}
                {errors.name && (
                  <Text
                    size="1"
                    color="red"
                  >
                    {t(`models.${errors.name.message}`)}
                  </Text>
                )}
              </Flex>

              {/* 任务类型 */}
              <Flex
                direction="column"
                gap="2"
              >
                <Text
                  size="2"
                  weight="medium"
                  color="gray"
                >
                  {t("models.taskType")}{" "}
                  <Text
                    color="red"
                    className="model-form-dialog__required-mark"
                  >
                    *
                  </Text>
                </Text>
                <Controller
                  name="taskType"
                  control={control}
                  render={({ field }) => (
                    <LabeledSelect
                      value={field.value}
                      options={[
                        { value: "llm", label: t("models.taskTypeLLM") },
                        { value: "embedding", label: t("models.taskTypeEmbedding") },
                        { value: "rerank", label: t("models.taskTypeRerank") },
                      ]}
                      onChange={handleTaskTypeChange}
                      triggerStyle={{ width: "100%" }}
                      placeholder={t("models.taskTypePlaceholder")}
                      disabled={isAgentSettingsLocked || parametersOnly}
                    />
                  )}
                />
                {errors.taskType && (
                  <Text
                    size="1"
                    color="red"
                  >
                    {t(`models.${errors.taskType.message}`)}
                  </Text>
                )}
              </Flex>

              {/* 提供商 */}
              <Flex
                direction="column"
                gap="2"
              >
                <Text
                  size="2"
                  weight="medium"
                  color="gray"
                >
                  {t("models.provider")}{" "}
                  <Text
                    color="red"
                    className="model-form-dialog__required-mark"
                  >
                    *
                  </Text>
                </Text>
                <Controller
                  name="providerId"
                  control={control}
                  render={({ field }) => (
                    <LabeledSelect
                      value={field.value}
                      options={filteredProviders.map((p) => ({
                        value: p.id,
                        label: getProviderOptionLabel(p),
                      }))}
                      onChange={handleProviderChange}
                      triggerStyle={{ width: "100%" }}
                      placeholder={t("models.providerPlaceholder")}
                      disabled={isAgentSettingsLocked || parametersOnly || Boolean(fixedProviderId)}
                    />
                  )}
                />
                {errors.providerId && (
                  <Text
                    size="1"
                    color="red"
                  >
                    {t(`models.${errors.providerId.message}`)}
                  </Text>
                )}
                {!providers || providers.length === 0 ? (
                  <Text
                    size="1"
                    color="gray"
                  >
                    {t("models.noProviders")}
                  </Text>
                ) : null}
              </Flex>

              {/* 模型 - 使用高级选择器 */}
              <Flex
                direction="column"
                gap="2"
                style={{
                  opacity: isModelSelectionDisabled ? 0.5 : 1,
                }}
              >
                <Text
                  size="2"
                  weight="medium"
                  color="gray"
                >
                  {t("models.modelId")}{" "}
                  <Text
                    color="red"
                    className="model-form-dialog__required-mark"
                  >
                    *
                  </Text>
                </Text>
                <Controller
                  name="modelId"
                  control={control}
                  render={({ field }) => (
                    <ModelIdSelect
                      value={field.value}
                      onChange={handleModelIdChange}
                      models={availableModels}
                      isLoading={loadingModels}
                      placeholder={t("models.modelIdPlaceholder")}
                      disabled={isAgentSettingsLocked || isModelSelectionDisabled || parametersOnly}
                      taskType={taskType as TaskType}
                      error={modelsError}
                      showRefreshButton={!parametersOnly}
                      onRefresh={remoteQuery.refresh}
                      isRefreshing={remoteQuery.isFetching || remoteQuery.isRefreshing}
                      refreshDisabled={
                        !providerId || remoteQuery.isFetching || remoteQuery.isRefreshing
                      }
                    />
                  )}
                />
                {errors.modelId && (
                  <Text
                    size="1"
                    color="red"
                  >
                    {t(`models.${errors.modelId.message}`)}
                  </Text>
                )}
                {selectedProvider &&
                  isCustomProviderType(selectedProvider.providerType) &&
                  !selectedCatalogProviderType &&
                  !loadingModels && (
                    <Text
                      size="1"
                      color="gray"
                    >
                      {t("models.noCatalogMatchHint")}
                    </Text>
                  )}
              </Flex>

              {taskType === "embedding" && selectedProviderSupportsEmbeddingDimensions && (
                <Flex
                  direction="column"
                  gap="2"
                >
                  <Text
                    size="2"
                    weight="medium"
                    color="gray"
                  >
                    {t("models.dimensions")}
                  </Text>
                  <Controller
                    name="dimensions"
                    control={control}
                    render={({ field }) => (
                      <TextField.Root
                        type="number"
                        min={1}
                        max={4096}
                        value={field.value?.toString() || ""}
                        onChange={(e) => {
                          const val = e.target.value;
                          field.onChange(val === "" ? null : Number(val));
                        }}
                        placeholder={t("models.dimensionsPlaceholder")}
                        disabled={isAgentSettingsLocked}
                      />
                    )}
                  />
                  {errors.dimensions && (
                    <Text
                      size="1"
                      color="red"
                    >
                      {t(`models.${errors.dimensions.message}`)}
                    </Text>
                  )}
                  <Text
                    size="1"
                    color="gray"
                  >
                    {t("models.dimensionsDesc")}
                  </Text>
                </Flex>
              )}

              {/* 备注 */}
              <Flex
                direction="column"
                gap="2"
              >
                <Text
                  size="2"
                  weight="medium"
                  color="gray"
                >
                  {t("models.remark")}
                </Text>
                <Controller
                  name="remark"
                  control={control}
                  render={({ field }) => (
                    <TextArea
                      {...field}
                      placeholder={t("models.remarkPlaceholder")}
                      rows={2}
                      disabled={isAgentSettingsLocked}
                    />
                  )}
                />
              </Flex>

              <Separator size="4" />

              {/* 高级参数 - 仅 LLM 模式 */}
              {taskType === "llm" && (
                <>
                  {speedVariants?.fast || defaultSpeed === "fast" ? (
                    <Flex
                      direction="column"
                      gap="2"
                    >
                      <Text
                        size="2"
                        weight="medium"
                        color="gray"
                      >
                        {t("models.defaultSpeed")}
                      </Text>
                      <Controller
                        name="defaultSpeed"
                        control={control}
                        render={({ field }) => (
                          <LabeledSelect
                            value={field.value}
                            onChange={field.onChange}
                            disabled={isAgentSettingsLocked}
                            options={[
                              { value: "standard", label: "Standard" },
                              { value: "fast", label: "Fast", disabled: !speedVariants?.fast },
                            ]}
                          />
                        )}
                      />
                      {speedUnavailable ? (
                        <Text
                          size="1"
                          color="amber"
                        >
                          {t("models.speedNoLongerAvailable")}
                        </Text>
                      ) : null}
                    </Flex>
                  ) : null}
                  <ModelMetadataSection
                    control={control}
                    modelId={model?.id}
                    disabled={isAgentSettingsLocked}
                  />
                  <AdvancedParamsSection
                    control={control}
                    modelId={model?.id}
                  />
                </>
              )}

              {/* 操作按钮 */}
              <Flex
                gap="3"
                mt="2"
                justify="end"
                className="model-form-dialog__footer"
              >
                <Dialog.Close>
                  <Button
                    type="button"
                    variant="soft"
                    color="gray"
                    disabled={isSubmitting}
                  >
                    {t("common.cancel")}
                  </Button>
                </Dialog.Close>
                <Button
                  type="submit"
                  disabled={
                    isAgentSettingsLocked || isSubmitting || hasDuplicateName || speedUnavailable
                  }
                >
                  {isSubmitting ? <Spinner size={18} /> : null}
                  {isEditing ? t("common.save") : t("common.create")}
                </Button>
              </Flex>
            </Flex>
          </form>
        </Box>
      </Dialog.Content>
    </Dialog.Root>
  );
}
