import { Box, Flex, Text, Button, IconButton, Tooltip, Badge } from "@radix-ui/themes";

import "./connections-settings.css";
/**
 * Connections Settings Component
 *
 * 外部连接设置面板，管理模型服务提供商连接。
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { Plus, Trash2, Edit, ListFilter } from "lucide-react";
import { useState, useCallback, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";

import { Spinner } from "@/components";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { QueryError } from "@/components/query-error";
import { toast } from "@/components/toast";
import type { ModelProvider } from "@/lib/model.types";

import {
  fetchProviders,
  fetchModelProviderCatalogProviders,
  fetchModels,
  fetchModelUsage,
  createProvider,
  updateProvider,
  deleteProvider,
} from "../lib/model-api";
import { ProviderIcon } from "../lib/provider-icons";
import {
  getProviderDisplayName,
  isCustomProviderType,
  resolveProviderDisplayName,
} from "../lib/provider-utils";
import { invalidateModelUses, useModelSync } from "../lib/use-model-sync";
import { AgentSettingsLockNotice } from "./agent-settings-lock-notice";
import { ConnectionFormDialog } from "./connection-form-dialog";
import { ProviderModelsDialog } from "./provider-models-dialog";

interface ConnectionsSettingsProps {
  managedProviderId?: string;
  onManagedProviderHandled?: () => void;
  isAgentSettingsLocked: boolean;
  isAgentSettingsLockLoading: boolean;
}

export function ConnectionsSettings({
  managedProviderId,
  onManagedProviderHandled,
  isAgentSettingsLocked,
  isAgentSettingsLockLoading,
}: ConnectionsSettingsProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const [formOpen, setFormOpen] = useState(false);
  const [editingConnection, setEditingConnection] = useState<ModelProvider | null>(null);
  const [deletingConnection, setDeletingConnection] = useState<ModelProvider | null>(null);
  const [modelsConnection, setModelsConnection] = useState<ModelProvider | null>(null);
  const [deletingUses, setDeletingUses] = useState<string[]>([]);

  useEffect(() => {
    if (!isAgentSettingsLocked) return;
    setFormOpen(false);
    setEditingConnection(null);
    setDeletingConnection(null);
    setModelsConnection(null);
  }, [isAgentSettingsLocked]);

  // 获取所有连接
  const {
    data: connections,
    isLoading: isConnectionsLoading,
    error: connectionsError,
    refetch: retryconnections,
  } = useQuery({
    queryKey: ["model-providers"],
    queryFn: fetchProviders,
  });
  useModelSync(connections);

  useEffect(() => {
    if (!managedProviderId || !connections) return;
    const connection = connections.find((entry) => entry.id === managedProviderId);
    if (connection) setModelsConnection(connection);
    onManagedProviderHandled?.();
  }, [managedProviderId, connections, onManagedProviderHandled]);

  const externalConnections = useMemo(
    () => connections?.filter((c) => !c.isBuiltin) ?? [],
    [connections],
  );

  const {
    data: catalogProviders,
    isLoading: isCatalogProvidersLoading,
    error: catalogProvidersError,
    refetch: retrycatalogProviders,
  } = useQuery({
    queryKey: ["model-provider-catalog", "providers"],
    queryFn: fetchModelProviderCatalogProviders,
  });

  // 创建连接
  const createMutation = useMutation({
    mutationFn: createProvider,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["model-providers"] });
      setFormOpen(false);
      toast.success(t("connections.createSuccess"));
    },
    onError: () => {
      toast.error(t("connections.createFailed"));
    },
  });

  // 更新连接
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: FormData }) => updateProvider(id, data),
    onSuccess: (_provider, { id }) => {
      queryClient.invalidateQueries({ queryKey: ["model-providers"] });
      void queryClient.invalidateQueries({ queryKey: ["provider-models", id] });
      void invalidateModelUses(queryClient);
      setFormOpen(false);
      setEditingConnection(null);
      toast.success(t("connections.updateSuccess"));
    },
    onError: (error) => {
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
      toast.error(typeof detail === "string" ? detail : t("connections.updateFailed"));
    },
  });

  // 删除连接
  const deleteMutation = useMutation({
    mutationFn: deleteProvider,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["model-providers"] });
      void invalidateModelUses(queryClient);
      setDeletingConnection(null);
      toast.success(t("connections.deleteSuccess"));
    },
    onError: () => {
      toast.error(t("connections.deleteFailed"));
    },
  });

  // 打开创建对话框
  const handleCreate = useCallback(() => {
    setEditingConnection(null);
    setFormOpen(true);
  }, []);

  // 打开编辑对话框
  const handleEdit = useCallback((connection: ModelProvider) => {
    setEditingConnection(connection);
    setFormOpen(true);
  }, []);

  // 提交表单
  const handleSubmit = useCallback(
    async (data: FormData) => {
      if (editingConnection) {
        await updateMutation.mutateAsync({
          id: editingConnection.id,
          data,
        });
      } else {
        await createMutation.mutateAsync(data);
      }
    },
    [editingConnection, createMutation, updateMutation],
  );

  // 确认删除
  const handleDelete = useCallback(
    async (connection: ModelProvider) => {
      try {
        const models = await fetchModels(connection.id, undefined, true);
        const uses = await Promise.all(models.map((model) => fetchModelUsage(model.id)));
        setDeletingUses([...new Set(uses.flat())]);
        setDeletingConnection(connection);
      } catch {
        toast.error(t("models.usageCheckFailed"));
      }
    },
    [t],
  );

  // 执行删除
  const handleConfirmDelete = useCallback(async () => {
    if (deletingConnection) {
      await deleteMutation.mutateAsync(deletingConnection.id);
    }
  }, [deletingConnection, deleteMutation]);

  const isContentLoading =
    isConnectionsLoading || isCatalogProvidersLoading || isAgentSettingsLockLoading;

  if (connectionsError || catalogProvidersError)
    return (
      <QueryError
        onRetry={() => {
          void retryconnections();
          void retrycatalogProviders();
        }}
      />
    );

  if (isContentLoading) {
    return (
      <Flex
        align="center"
        justify="center"
        className="connections-settings__content"
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
          {t("connections.description")}
        </Text>

        {/* 新建按钮 */}
        <Flex>
          <Button
            onClick={handleCreate}
            disabled={isAgentSettingsLocked}
          >
            <Plus size={16} />
            {t("connections.newConnection")}
          </Button>
        </Flex>

        {/* 连接列表 */}
        {externalConnections.length > 0 ? (
          <Flex direction="column">
            {externalConnections.map((connection, index) => (
              <Box
                key={connection.id}
                className="list-item-hover"
              >
                <Flex
                  align="center"
                  justify="between"
                  className="connections-settings__connection-row"
                >
                  <Flex
                    align="center"
                    gap="3"
                    className="connections-settings__connection-info"
                  >
                    {/* 图标 */}
                    <Box className="connections-settings__provider-icon">
                      <ProviderIcon
                        iconPath={connection.iconPath}
                        size={24}
                      />
                    </Box>

                    {/* 信息 */}
                    <Flex
                      direction="column"
                      gap="1"
                      className="connections-settings__connection-info"
                    >
                      <Flex
                        align="center"
                        gap="2"
                      >
                        <Text
                          size="3"
                          weight="medium"
                        >
                          {connection.name ||
                            (isCustomProviderType(connection.providerType)
                              ? connection.url
                              : null) ||
                            resolveProviderDisplayName(connection)}
                        </Text>
                      </Flex>
                      <Flex
                        align="center"
                        gap="2"
                      >
                        <Text
                          size="2"
                          color="gray"
                        >
                          {connection.catalogMatch?.displayName ||
                            getProviderDisplayName(connection.providerType)}
                        </Text>
                        {connection.unavailableTaskTypes.length > 0 && (
                          <Badge
                            color="amber"
                            variant="soft"
                          >
                            {t("connections.optionalSdkRequired")}
                          </Badge>
                        )}
                        {isCustomProviderType(connection.providerType) &&
                          !connection.catalogMatch && (
                            <>
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
                                {connection.url}
                              </Text>
                            </>
                          )}
                      </Flex>
                    </Flex>
                  </Flex>

                  {/* 操作按钮 */}
                  <Flex gap="2">
                    <Tooltip content={t("models.manageModels")}>
                      <IconButton
                        variant="ghost"
                        color="gray"
                        aria-label={t("models.manageModels")}
                        onClick={() => setModelsConnection(connection)}
                        disabled={isAgentSettingsLocked}
                      >
                        <ListFilter size={16} />
                      </IconButton>
                    </Tooltip>
                    <IconButton
                      variant="ghost"
                      color="gray"
                      aria-label={t("common.edit")}
                      onClick={() => handleEdit(connection)}
                      disabled={isAgentSettingsLocked}
                    >
                      <Edit size={16} />
                    </IconButton>
                    <IconButton
                      variant="ghost"
                      color="red"
                      aria-label={t("common.delete")}
                      onClick={() => handleDelete(connection)}
                      disabled={isAgentSettingsLocked}
                    >
                      <Trash2 size={16} />
                    </IconButton>
                  </Flex>
                </Flex>
                {index < externalConnections.length - 1 && (
                  <Box className="connections-settings__divider" />
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
            className="connections-settings__empty-state"
          >
            <Text
              size="2"
              color="gray"
            >
              {t("connections.noConnections")}
            </Text>
          </Flex>
        )}
      </Flex>

      {/* 表单对话框 */}
      <ConnectionFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        connection={editingConnection || undefined}
        catalogProviders={catalogProviders}
        isCatalogLoading={isCatalogProvidersLoading}
        onSubmit={handleSubmit}
        isSubmitting={createMutation.isPending || updateMutation.isPending}
        isAgentSettingsLocked={isAgentSettingsLocked}
      />

      <ProviderModelsDialog
        provider={modelsConnection}
        open={Boolean(modelsConnection)}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) setModelsConnection(null);
        }}
        isAgentSettingsLocked={isAgentSettingsLocked}
      />

      {/* 删除确认对话框 */}
      <ConfirmDialog
        open={!!deletingConnection}
        onOpenChange={(open) => !open && setDeletingConnection(null)}
        title={t("connections.deleteConnection")}
        description={[
          t("connections.deleteConfirm"),
          deletingUses.length > 0
            ? t("models.affectedUses", { uses: deletingUses.join("、") })
            : "",
        ]
          .filter(Boolean)
          .join("\n")}
        onConfirm={handleConfirmDelete}
        confirmText={t("common.delete")}
        cancelText={t("common.cancel")}
        loading={deleteMutation.isPending}
      />
    </Box>
  );
}
