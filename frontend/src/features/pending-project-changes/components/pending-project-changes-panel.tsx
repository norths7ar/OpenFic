import { Badge, Button, Flex, ScrollArea, Text } from "@radix-ui/themes";
import axios from "axios";
import { CheckCircle2, FileClock, XCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { ConfirmDialog, Spinner, toast } from "@/components";

import {
  useApplyPendingProjectChange,
  usePendingProjectChangeCount,
  usePendingProjectChanges,
  useRejectPendingProjectChange,
} from "../hooks";
import type { JsonValue, PendingProjectChange } from "../types";

import "./pending-project-changes-dialog.css";

const EMPTY_PENDING_PROJECT_CHANGES: PendingProjectChange[] = [];

function formatJson(value: JsonValue): string {
  return JSON.stringify(value, null, 2);
}

function formatCreatedAt(value: string, locale: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "medium" }).format(date);
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "";
}

function ChangeMetadata({ label, value }: { label: string; value: string }) {
  return (
    <div className="pending-project-changes-metadata-item">
      <Text
        size="1"
        color="gray"
      >
        {label}
      </Text>
      <Text
        size="2"
        className="pending-project-changes-metadata-value"
      >
        {value}
      </Text>
    </div>
  );
}

function JsonSection({ label, value }: { label: string; value: JsonValue }) {
  return (
    <section className="pending-project-changes-json-section">
      <Text
        size="2"
        weight="medium"
      >
        {label}
      </Text>
      <pre>{formatJson(value)}</pre>
    </section>
  );
}

export function PendingProjectChangesPanel({
  projectId,
  className,
}: {
  projectId: string;
  className?: string;
}) {
  const { t, i18n } = useTranslation();
  const [selectedChangeId, setSelectedChangeId] = useState<string | null>(null);
  const [changeToReject, setChangeToReject] = useState<PendingProjectChange | null>(null);
  const [changeToApply, setChangeToApply] = useState<PendingProjectChange | null>(null);
  const changesQuery = usePendingProjectChanges(projectId, "pending");
  const countQuery = usePendingProjectChangeCount(projectId);
  const rejectMutation = useRejectPendingProjectChange(projectId);
  const applyMutation = useApplyPendingProjectChange(projectId);
  const changes = changesQuery.data ?? EMPTY_PENDING_PROJECT_CHANGES;
  const selectedChange = useMemo(
    () => changes.find((change) => change.id === selectedChangeId) ?? changes[0] ?? null,
    [changes, selectedChangeId],
  );

  useEffect(() => {
    if (!changes.length) {
      setSelectedChangeId(null);
    } else if (!changes.some((change) => change.id === selectedChangeId)) {
      setSelectedChangeId(changes[0].id);
    }
  }, [changes, selectedChangeId]);

  const handleReject = () => {
    if (!changeToReject) return;
    rejectMutation.mutate(changeToReject.id, {
      onSuccess: () => {
        toast.success(t("pendingProjectChanges.rejectSuccess"));
        setChangeToReject(null);
      },
      onError: (error) => {
        toast.error(
          t("pendingProjectChanges.rejectFailed", {
            error: getErrorMessage(error) || t("pendingProjectChanges.unknownError"),
          }),
        );
      },
    });
  };

  const handleApply = () => {
    if (!changeToApply) return;
    applyMutation.mutate(changeToApply.id, {
      onSuccess: () => {
        toast.success(t("pendingProjectChanges.applySuccess"));
        setChangeToApply(null);
      },
      onError: (error) => {
        if (axios.isAxiosError(error) && error.response?.status === 409) {
          toast.error(t("pendingProjectChanges.applyConflict"));
          return;
        }
        toast.error(
          t("pendingProjectChanges.applyFailed", {
            error: getErrorMessage(error) || t("pendingProjectChanges.unknownError"),
          }),
        );
      },
    });
  };

  const pendingCount = countQuery.data?.count ?? 0;
  const panelClassName = ["pending-project-changes-panel", className].filter(Boolean).join(" ");

  return (
    <>
      <Flex
        align="center"
        justify="between"
        gap="3"
        mb="3"
      >
        <Text
          size="2"
          color="gray"
        >
          {t("pendingProjectChanges.description", { count: pendingCount })}
        </Text>
        <Badge
          color="amber"
          variant="soft"
        >
          {pendingCount}
        </Badge>
      </Flex>
      <div className={panelClassName}>
        {changesQuery.isLoading ? (
          <Flex
            className="pending-project-changes-state"
            direction="column"
            align="center"
            justify="center"
            gap="2"
          >
            <Spinner size={18} />
            <Text
              size="2"
              color="gray"
            >
              {t("pendingProjectChanges.loading")}
            </Text>
          </Flex>
        ) : changesQuery.isError ? (
          <Flex
            className="pending-project-changes-state"
            direction="column"
            align="center"
            justify="center"
            gap="3"
          >
            <Text
              size="2"
              color="red"
            >
              {t("pendingProjectChanges.loadFailed", {
                error:
                  getErrorMessage(changesQuery.error) || t("pendingProjectChanges.unknownError"),
              })}
            </Text>
            <Button
              size="2"
              variant="soft"
              onClick={() => void changesQuery.refetch()}
            >
              {t("pendingProjectChanges.retry")}
            </Button>
          </Flex>
        ) : !changes.length ? (
          <Flex
            className="pending-project-changes-state"
            direction="column"
            align="center"
            justify="center"
            gap="2"
          >
            <FileClock
              size={22}
              aria-hidden="true"
            />
            <Text
              size="2"
              color="gray"
            >
              {t("pendingProjectChanges.empty")}
            </Text>
          </Flex>
        ) : (
          <div className="pending-project-changes-layout">
            <ScrollArea className="pending-project-changes-list-scroll">
              <div className="pending-project-changes-list">
                {changes.map((change) => (
                  <button
                    type="button"
                    className="pending-project-changes-list-item"
                    data-selected={change.id === selectedChange?.id}
                    key={change.id}
                    onClick={() => setSelectedChangeId(change.id)}
                  >
                    <Text
                      size="2"
                      weight="medium"
                    >
                      {change.target_type}
                    </Text>
                    <Text
                      size="1"
                      color="gray"
                    >
                      {change.operation} · {formatCreatedAt(change.created_at, i18n.language)}
                    </Text>
                  </button>
                ))}
              </div>
            </ScrollArea>
            {selectedChange ? (
              <ScrollArea className="pending-project-changes-detail-scroll">
                <div className="pending-project-changes-detail">
                  <Flex
                    align="center"
                    justify="between"
                    gap="3"
                  >
                    <Text
                      size="3"
                      weight="medium"
                    >
                      {selectedChange.target_type}
                    </Text>
                    <Flex gap="2">
                      {selectedChange.is_applicable ? (
                        <Button
                          size="1"
                          color="green"
                          onClick={() => setChangeToApply(selectedChange)}
                          disabled={rejectMutation.isPending}
                        >
                          <CheckCircle2 size={14} />
                          {t("pendingProjectChanges.apply")}
                        </Button>
                      ) : (
                        <Badge
                          color="gray"
                          title={selectedChange.applicability_reason ?? undefined}
                        >
                          {t("pendingProjectChanges.notApplicable")}
                        </Badge>
                      )}
                      <Button
                        size="1"
                        color="red"
                        variant="soft"
                        onClick={() => setChangeToReject(selectedChange)}
                        disabled={applyMutation.isPending}
                      >
                        <XCircle size={14} />
                        {t("pendingProjectChanges.reject")}
                      </Button>
                    </Flex>
                  </Flex>
                  <div className="pending-project-changes-metadata">
                    <ChangeMetadata
                      label={t("pendingProjectChanges.targetType")}
                      value={selectedChange.target_type}
                    />
                    <ChangeMetadata
                      label={t("pendingProjectChanges.targetId")}
                      value={selectedChange.target_id ?? t("pendingProjectChanges.none")}
                    />
                    <ChangeMetadata
                      label={t("pendingProjectChanges.operation")}
                      value={selectedChange.operation}
                    />
                    <ChangeMetadata
                      label={t("pendingProjectChanges.createdAt")}
                      value={formatCreatedAt(selectedChange.created_at, i18n.language)}
                    />
                    <ChangeMetadata
                      label={t("pendingProjectChanges.model")}
                      value={selectedChange.model_id ?? t("pendingProjectChanges.none")}
                    />
                    <ChangeMetadata
                      label={t("pendingProjectChanges.sourceTask")}
                      value={selectedChange.source_task_id ?? t("pendingProjectChanges.none")}
                    />
                    <ChangeMetadata
                      label={t("pendingProjectChanges.sourceMessage")}
                      value={selectedChange.source_message_id ?? t("pendingProjectChanges.none")}
                    />
                  </div>
                  <JsonSection
                    label={t("pendingProjectChanges.before")}
                    value={selectedChange.before}
                  />
                  <JsonSection
                    label={t("pendingProjectChanges.after")}
                    value={selectedChange.after}
                  />
                </div>
              </ScrollArea>
            ) : null}
          </div>
        )}
      </div>
      <ConfirmDialog
        open={Boolean(changeToApply)}
        onOpenChange={(nextOpen) => {
          if (!nextOpen && !applyMutation.isPending) setChangeToApply(null);
        }}
        onConfirm={handleApply}
        title={t("pendingProjectChanges.applyConfirmTitle")}
        description={t(
          changeToApply?.operation === "delete"
            ? "pendingProjectChanges.applyDeleteConfirmDescription"
            : "pendingProjectChanges.applyConfirmDescription",
        )}
        confirmText={t("pendingProjectChanges.apply")}
        confirmColor={changeToApply?.operation === "delete" ? "red" : "green"}
        cancelText={t("common.cancel")}
        loading={applyMutation.isPending}
      />
      <ConfirmDialog
        open={Boolean(changeToReject)}
        onOpenChange={(nextOpen) => {
          if (!nextOpen && !rejectMutation.isPending) setChangeToReject(null);
        }}
        onConfirm={handleReject}
        title={t("pendingProjectChanges.rejectConfirmTitle")}
        description={t("pendingProjectChanges.rejectConfirmDescription")}
        confirmText={t("pendingProjectChanges.reject")}
        cancelText={t("common.cancel")}
        loading={rejectMutation.isPending}
      />
    </>
  );
}
