import {
  Badge,
  Box,
  Button,
  Dialog,
  Flex,
  ScrollArea,
  Switch,
  Tabs,
  Text,
  TextField,
} from "@radix-ui/themes";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { CircleCheck, RefreshCw, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  CapabilityIcon,
  ContextBadge,
  formatContextWindow,
  getModelCapabilityKeys,
} from "@/components/model-capability-tags";
import { Spinner } from "@/components/spinner";
import { toast } from "@/components/toast";
import type { AvailableModel, Model, ModelProvider, TaskType } from "@/lib/model.types";

import {
  createModel,
  fetchModels,
  fetchProviderModels,
  updateModel,
  validateModel,
} from "../lib/model-api";

interface ProviderModelsDialogProps {
  provider: ModelProvider | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  isAgentSettingsLocked: boolean;
}

interface ProviderModelRow {
  remote: AvailableModel;
  saved: Model | null;
  isRemoteAvailable: boolean;
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string" && detail) return detail;
  }
  return error instanceof Error && error.message ? error.message : fallback;
}

function uniqueModelName(name: string, models: Model[]): string {
  const names = new Set(models.map((model) => model.name));
  if (!names.has(name)) return name;
  let suffix = 2;
  while (names.has(`${name} (${suffix})`)) suffix += 1;
  return `${name} (${suffix})`;
}

function toAvailableModel(model: Model): AvailableModel {
  return {
    id: model.modelId,
    name: model.name,
    taskType: model.taskType,
    reasoning: null,
    toolCall: null,
    inputModalities: [],
    contextWindow: model.contextLength,
    inputPricePerMillion: model.inputPrice || null,
    outputPricePerMillion: model.outputPrice || null,
    cacheReadPricePerMillion: model.cacheReadPrice || null,
    cacheWritePricePerMillion: model.cacheWritePrice || null,
    source: "remote",
  };
}

export function ProviderModelsDialog({
  provider,
  open,
  onOpenChange,
  isAgentSettingsLocked,
}: ProviderModelsDialogProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [taskType, setTaskType] = useState<TaskType>("llm");
  const [searchQuery, setSearchQuery] = useState("");
  const [pendingModelId, setPendingModelId] = useState<string | null>(null);
  const [validatingModelId, setValidatingModelId] = useState<string | null>(null);

  const supportedTaskTypes = useMemo<TaskType[]>(() => {
    const supported = provider?.supportedTaskTypes ?? [];
    const ordered = (["llm", "embedding", "rerank"] as TaskType[]).filter((type) =>
      supported.includes(type),
    );
    return ordered.length > 0 ? ordered : ["llm"];
  }, [provider]);

  useEffect(() => {
    if (!open) return;
    setSearchQuery("");
    setTaskType(supportedTaskTypes[0] ?? "llm");
  }, [open, provider?.id, supportedTaskTypes]);

  const remoteQuery = useQuery({
    queryKey: ["provider-models", provider?.id, taskType],
    queryFn: () => fetchProviderModels(provider!.id, taskType),
    enabled: open && Boolean(provider) && supportedTaskTypes.includes(taskType),
  });

  const savedQuery = useQuery({
    queryKey: ["models", "include-disabled"],
    queryFn: () => fetchModels(undefined, undefined, true),
    enabled: open && Boolean(provider),
  });

  const providerModels = useMemo(
    () =>
      (savedQuery.data ?? []).filter(
        (model) => model.providerId === provider?.id && model.taskType === taskType,
      ),
    [provider?.id, savedQuery.data, taskType],
  );

  const rows = useMemo<ProviderModelRow[]>(() => {
    const savedByIdentifier = new Map(
      providerModels.map((model) => [model.modelId, model] as const),
    );
    const remoteModels = remoteQuery.data?.models ?? [];
    const result = remoteModels.map((remote) => ({
      remote,
      saved: savedByIdentifier.get(remote.id) ?? null,
      isRemoteAvailable: true,
    }));
    const remoteIds = new Set(remoteModels.map((model) => model.id));
    result.push(
      ...providerModels
        .filter((model) => model.isEnabled && !remoteIds.has(model.modelId))
        .map((model) => ({
          remote: toAvailableModel(model),
          saved: model,
          isRemoteAvailable: false,
        })),
    );
    return result;
  }, [providerModels, remoteQuery.data?.models]);

  const filteredRows = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return rows;
    return rows.filter(
      ({ remote }) =>
        remote.name.toLowerCase().includes(query) || remote.id.toLowerCase().includes(query),
    );
  }, [rows, searchQuery]);

  const enabledCount = providerModels.filter((model) => model.isEnabled).length;
  const isTaskUnavailable = provider?.unavailableTaskTypes.includes(taskType) ?? false;

  const toggleMutation = useMutation({
    mutationFn: async ({ row, enabled }: { row: ProviderModelRow; enabled: boolean }) => {
      setPendingModelId(row.remote.id);
      if (row.saved) {
        return updateModel(row.saved.id, { is_enabled: enabled });
      }
      if (!provider) throw new Error(t("models.providerRequired"));
      const allModels = savedQuery.data ?? [];
      return createModel({
        name: uniqueModelName(row.remote.name || row.remote.id, allModels),
        provider_id: provider.id,
        model_id: row.remote.id,
        task_type: taskType,
        context_length: row.remote.contextWindow ?? 0,
        input_price: row.remote.inputPricePerMillion ?? 0,
        output_price: row.remote.outputPricePerMillion ?? 0,
        cache_read_price: row.remote.cacheReadPricePerMillion ?? 0,
        cache_write_price: row.remote.cacheWritePricePerMillion ?? 0,
        is_enabled: true,
      });
    },
    onSuccess: (_model, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["models"] });
      toast.success(variables.enabled ? t("models.modelEnabled") : t("models.modelDisabled"));
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, t("models.updateFailed")));
    },
    onSettled: () => setPendingModelId(null),
  });

  const validateMutation = useMutation({
    mutationFn: async (model: Model) => {
      setValidatingModelId(model.id);
      return validateModel(model.id);
    },
    onSuccess: (result) => {
      if (result.success) {
        toast.success(result.message);
        return;
      }
      toast.error(result.detail ? `${result.message} ${result.detail}` : result.message);
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, t("models.validationRequestFailed")));
    },
    onSettled: () => setValidatingModelId(null),
  });

  const isLoading = remoteQuery.isLoading || savedQuery.isLoading;

  return (
    <Dialog.Root
      open={open}
      onOpenChange={onOpenChange}
    >
      <Dialog.Content style={{ maxWidth: 760 }}>
        <Dialog.Title>
          {t("models.manageProviderModels", { provider: provider?.name || provider?.url || "" })}
        </Dialog.Title>
        <Dialog.Description>{t("models.manageProviderModelsDescription")}</Dialog.Description>

        <Flex
          direction="column"
          gap="3"
          mt="4"
        >
          {supportedTaskTypes.length > 1 ? (
            <Tabs.Root
              value={taskType}
              onValueChange={(value) => setTaskType(value as TaskType)}
            >
              <Tabs.List>
                {supportedTaskTypes.map((type) => (
                  <Tabs.Trigger
                    key={type}
                    value={type}
                  >
                    {t(`models.taskTypes.${type}`)}
                  </Tabs.Trigger>
                ))}
              </Tabs.List>
            </Tabs.Root>
          ) : null}

          {isTaskUnavailable ? (
            <Text
              size="2"
              color="amber"
            >
              {t("models.optionalSdkRequired")}
            </Text>
          ) : null}

          <Flex
            align="center"
            justify="between"
            gap="3"
          >
            <TextField.Root
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder={t("models.searchModel")}
              style={{ flex: 1 }}
            >
              <TextField.Slot>
                <Search size={15} />
              </TextField.Slot>
            </TextField.Root>
            <Text
              size="2"
              color="gray"
              style={{ whiteSpace: "nowrap" }}
            >
              {t("models.enabledModelCount", { enabled: enabledCount, total: rows.length })}
            </Text>
            <Button
              variant="soft"
              color="gray"
              onClick={() => void remoteQuery.refetch()}
              disabled={remoteQuery.isFetching}
            >
              {remoteQuery.isFetching ? <Spinner size={12} /> : <RefreshCw size={15} />}
              {t("models.detectModels")}
            </Button>
          </Flex>

          {isLoading ? (
            <Flex
              align="center"
              justify="center"
              style={{ height: 280 }}
            >
              <Spinner size={18} />
            </Flex>
          ) : remoteQuery.isError ? (
            <Flex
              direction="column"
              align="center"
              justify="center"
              gap="2"
              style={{ height: 280 }}
            >
              <Text color="red">{t("models.fetchModelsFailed")}</Text>
              <Text
                size="2"
                color="gray"
              >
                {getErrorMessage(remoteQuery.error, t("models.networkRequestFailed"))}
              </Text>
            </Flex>
          ) : (
            <ScrollArea style={{ height: 420 }}>
              <Flex direction="column">
                {filteredRows.map((row) => {
                  const capabilities = getModelCapabilityKeys(row.remote);
                  const contextLabel = formatContextWindow(row.remote.contextWindow);
                  const isPending = pendingModelId === row.remote.id;
                  const isValidating = row.saved?.id === validatingModelId;
                  return (
                    <Box
                      key={`${taskType}-${row.remote.id}`}
                      style={{ borderBottom: "1px solid var(--gray-a4)" }}
                    >
                      <Flex
                        align="center"
                        justify="between"
                        gap="4"
                        py="3"
                        px="2"
                      >
                        <Flex
                          direction="column"
                          gap="1"
                          style={{ minWidth: 0, flex: 1 }}
                        >
                          <Flex
                            align="center"
                            gap="2"
                            wrap="wrap"
                          >
                            <Text weight="medium">{row.remote.name}</Text>
                            {capabilities.map((capability) => (
                              <CapabilityIcon
                                key={capability}
                                capability={capability}
                              />
                            ))}
                            {contextLabel ? <ContextBadge label={contextLabel} /> : null}
                            {!row.isRemoteAvailable ? (
                              <Badge
                                color="amber"
                                variant="soft"
                              >
                                {t("models.notDetectedRemotely")}
                              </Badge>
                            ) : null}
                          </Flex>
                          <Text
                            size="1"
                            color="gray"
                            truncate
                          >
                            {row.remote.id}
                          </Text>
                        </Flex>
                        {isPending || isValidating ? (
                          <Spinner size={18} />
                        ) : (
                          <Flex
                            align="center"
                            gap="2"
                          >
                            {row.saved ? (
                              <Button
                                variant="soft"
                                color="gray"
                                size="1"
                                onClick={() => validateMutation.mutate(row.saved!)}
                                disabled={validateMutation.isPending}
                              >
                                <CircleCheck size={14} />
                                {t("models.validateModel")}
                              </Button>
                            ) : null}
                            <Switch
                              checked={row.saved?.isEnabled ?? false}
                              disabled={
                                isAgentSettingsLocked ||
                                toggleMutation.isPending ||
                                row.saved?.isBuiltin ||
                                (isTaskUnavailable && !row.saved)
                              }
                              aria-label={t("models.toggleModel", { model: row.remote.name })}
                              onCheckedChange={(enabled) => toggleMutation.mutate({ row, enabled })}
                            />
                          </Flex>
                        )}
                      </Flex>
                    </Box>
                  );
                })}
                {filteredRows.length === 0 ? (
                  <Flex
                    align="center"
                    justify="center"
                    style={{ height: 240 }}
                  >
                    <Text color="gray">{t("models.noModelsAvailable")}</Text>
                  </Flex>
                ) : null}
              </Flex>
            </ScrollArea>
          )}
        </Flex>

        <Flex
          justify="end"
          mt="4"
        >
          <Dialog.Close>
            <Button
              variant="soft"
              color="gray"
            >
              {t("common.close")}
            </Button>
          </Dialog.Close>
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
}
