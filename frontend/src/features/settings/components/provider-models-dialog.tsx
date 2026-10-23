import "./provider-models-dialog.css";
import {
  Box,
  Button,
  Dialog,
  Flex,
  IconButton,
  ScrollArea,
  Switch,
  Tabs,
  Text,
  TextField,
} from "@radix-ui/themes";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { CircleCheck, Plus, RefreshCw, Search, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/confirm-dialog";
import {
  CapabilityIcon,
  ContextBadge,
  formatContextWindow,
  getModelCapabilityKeys,
} from "@/components/model-capability-tags";
import { ModelDiscoveryStatus } from "@/components/model-discovery-status";
import { Spinner } from "@/components/spinner";
import { toast } from "@/components/toast";
import { MODEL_DISCOVERY_QUERY_OPTIONS } from "@/lib/model-discovery";
import type {
  AvailableModel,
  Model,
  ModelProvider,
  TaskType,
  ModelCreateRequest,
  ModelUpdateRequest,
} from "@/lib/model.types";

import {
  createModel,
  deleteModel,
  fetchModelUsage,
  fetchModels,
  updateModel,
  validateModel,
} from "../lib/model-api";
import { invalidateModelUses } from "../lib/use-model-sync";
import { useProviderModelsQuery } from "../lib/use-provider-models-query";
import { ModelFormDialog } from "./model-form-dialog";

interface ProviderModelsDialogProps {
  provider: ModelProvider | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  isAgentSettingsLocked: boolean;
}

interface ProviderModelRow {
  remote: AvailableModel;
  saved: Model | null;
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
  const [manualAddOpen, setManualAddOpen] = useState(false);
  const [confirmation, setConfirmation] = useState<{
    row: ProviderModelRow;
    action: "disable" | "delete";
    uses: string[];
  } | null>(null);
  const [checkingUsage, setCheckingUsage] = useState(false);

  const savedQuery = useQuery({
    ...MODEL_DISCOVERY_QUERY_OPTIONS,
    queryKey: ["models", "include-disabled"],
    queryFn: () => fetchModels(undefined, undefined, true),
    enabled: open && Boolean(provider),
  });

  const supportedTaskTypes = useMemo<TaskType[]>(() => {
    const supported = [
      ...(provider?.supportedTaskTypes ?? []),
      ...(savedQuery.data ?? [])
        .filter((model) => model.providerId === provider?.id)
        .map((model) => model.taskType),
    ];
    const ordered = (["llm", "embedding", "rerank"] as TaskType[]).filter((type) =>
      supported.includes(type),
    );
    return ordered.length > 0 ? ordered : ["llm"];
  }, [provider, savedQuery.data]);

  const firstTaskType = supportedTaskTypes[0] ?? "llm";
  useEffect(() => {
    if (!open) return;
    setSearchQuery("");
    setTaskType(firstTaskType);
  }, [open, provider?.id, firstTaskType]);

  const remoteQuery = useProviderModelsQuery(
    provider?.id,
    taskType,
    open && supportedTaskTypes.includes(taskType),
  );

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
    }));
    const remoteIds = new Set(
      remoteModels.flatMap((model) => [model.id, ...Object.values(model.speedVariants ?? {})]),
    );
    result.push(
      ...providerModels
        .filter((model) => !remoteIds.has(model.modelId))
        .map((model) => ({
          remote: toAvailableModel(model),
          saved: model,
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
      void invalidateModelUses(queryClient);
      toast.success(variables.enabled ? t("models.modelEnabled") : t("models.modelDisabled"));
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, t("models.updateFailed")));
    },
    onSettled: () => setPendingModelId(null),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteModel,
    onSuccess: () => {
      void invalidateModelUses(queryClient);
      toast.success(t("models.deleteSuccess"));
    },
    onError: (error) => toast.error(getErrorMessage(error, t("models.deleteFailed"))),
  });

  const manualAddMutation = useMutation({
    mutationFn: (data: ModelCreateRequest | ModelUpdateRequest) =>
      createModel(data as ModelCreateRequest),
    onSuccess: () => {
      void invalidateModelUses(queryClient);
      setManualAddOpen(false);
      toast.success(t("models.createSuccess"));
    },
    onError: (error) => toast.error(getErrorMessage(error, t("models.createFailed"))),
  });

  const requestRemoval = async (row: ProviderModelRow, action: "disable" | "delete") => {
    if (!row.saved) return;
    setCheckingUsage(true);
    try {
      const uses = await fetchModelUsage(row.saved.id);
      setConfirmation({ row, action, uses });
    } catch {
      toast.error(t("models.usageCheckFailed"));
    } finally {
      setCheckingUsage(false);
    }
  };

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
      <Dialog.Content
        className="provider-models-dialog"
        maxWidth="760px"
      >
        <Dialog.Title>
          {t("models.manageProviderModels", { provider: provider?.name || provider?.url || "" })}
        </Dialog.Title>
        <Dialog.Description>{t("models.manageProviderModelsDescription")}</Dialog.Description>

        <Flex
          className="provider-models-dialog-body"
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
              onClick={remoteQuery.refresh}
              disabled={remoteQuery.isFetching || remoteQuery.isRefreshing}
            >
              {remoteQuery.isFetching || remoteQuery.isRefreshing ? (
                <Spinner size={12} />
              ) : (
                <RefreshCw size={15} />
              )}
              {t("models.detectModels")}
            </Button>
          </Flex>

          <Text
            size="1"
            color="gray"
          >
            {t("models.autoRefreshModels")}
          </Text>
          <Flex justify="end">
            <Button
              size="2"
              variant="soft"
              color="gray"
              onClick={() => setManualAddOpen(true)}
              disabled={isAgentSettingsLocked || isTaskUnavailable}
            >
              <Plus size={15} />
              {t("models.manualAddModel")}
            </Button>
          </Flex>
          {remoteQuery.isError || remoteQuery.data?.discoveryStatus === "error" ? (
            <Text
              size="2"
              color="gray"
              role="status"
            >
              {t("models.discoveryFailed")} ·{" "}
              {remoteQuery.error
                ? getErrorMessage(remoteQuery.error, t("models.networkRequestFailed"))
                : t("models.discoveryFailedHint")}
            </Text>
          ) : null}

          {isLoading ? (
            <Flex
              align="center"
              justify="center"
              style={{ height: 280 }}
            >
              <Spinner size={18} />
            </Flex>
          ) : (
            <ScrollArea className="provider-models-dialog-list">
              <Flex direction="column">
                {filteredRows.map((row) => {
                  const capabilities = getModelCapabilityKeys(row.remote);
                  const contextLabel = formatContextWindow(row.remote.contextWindow);
                  const isPending = pendingModelId === row.remote.id;
                  const isValidating = row.saved?.id === validatingModelId;
                  const discovery = remoteQuery.data;
                  const statusModel = row.saved
                    ? {
                        ...row.saved,
                        discoveryStatus: remoteQuery.isError
                          ? ("error" as const)
                          : discovery?.discoveryStatus,
                        upstreamStatus:
                          remoteQuery.isError || discovery?.discoveryStatus !== "ok"
                            ? ("unknown" as const)
                            : discovery.models.some((entry) => entry.id === row.remote.id)
                              ? ("listed" as const)
                              : ("not_listed" as const),
                        discoveryCheckedAt:
                          discovery?.discoveryCheckedAt ?? row.saved.discoveryCheckedAt,
                      }
                    : null;
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
                            {row.remote.speedVariants?.fast ? (
                              <Text
                                size="1"
                                color="gray"
                              >
                                Standard / Fast
                              </Text>
                            ) : null}
                            {capabilities.map((capability) => (
                              <CapabilityIcon
                                key={capability}
                                capability={capability}
                              />
                            ))}
                            {contextLabel ? <ContextBadge label={contextLabel} /> : null}
                            {statusModel ? (
                              <ModelDiscoveryStatus
                                model={statusModel}
                                compact
                              />
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
                              <IconButton
                                size="1"
                                variant="ghost"
                                color="red"
                                aria-label={t("models.deleteModel")}
                                onClick={() => requestRemoval(row, "delete")}
                                disabled={
                                  isAgentSettingsLocked || checkingUsage || row.saved.isBuiltin
                                }
                              >
                                <Trash2 size={14} />
                              </IconButton>
                            ) : null}
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
                                checkingUsage ||
                                row.saved?.isBuiltin ||
                                (isTaskUnavailable && !row.saved)
                              }
                              aria-label={t("models.toggleModel", { model: row.remote.name })}
                              onCheckedChange={(enabled) =>
                                enabled
                                  ? toggleMutation.mutate({ row, enabled })
                                  : void requestRemoval(row, "disable")
                              }
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

        <ModelFormDialog
          open={manualAddOpen}
          onOpenChange={setManualAddOpen}
          fixedProviderId={provider?.id}
          initialTaskType={taskType}
          models={savedQuery.data ?? []}
          onSubmit={async (data) => {
            await manualAddMutation.mutateAsync(data);
          }}
          isSubmitting={manualAddMutation.isPending}
          isAgentSettingsLocked={isAgentSettingsLocked}
        />
        <ConfirmDialog
          open={Boolean(confirmation)}
          onOpenChange={(next) => {
            if (!next) setConfirmation(null);
          }}
          title={t(
            confirmation?.action === "delete" ? "models.deleteModel" : "models.disableModel",
          )}
          description={[
            t(
              confirmation?.row.saved?.taskType === "llm"
                ? confirmation.action === "delete"
                  ? "models.deleteConfirm"
                  : "models.disableConfirm"
                : "models.indexModelChangeConfirm",
            ),
            confirmation?.uses.length
              ? t("models.affectedUses", { uses: confirmation.uses.join("、") })
              : "",
          ]
            .filter(Boolean)
            .join("\n")}
          onConfirm={() => {
            if (!confirmation?.row.saved) return;
            if (confirmation.action === "delete") deleteMutation.mutate(confirmation.row.saved.id);
            else toggleMutation.mutate({ row: confirmation.row, enabled: false });
          }}
          confirmText={t(confirmation?.action === "delete" ? "common.delete" : "common.confirm")}
          loading={toggleMutation.isPending || deleteMutation.isPending}
        />

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
