import {
  Badge,
  Box,
  Button,
  DropdownMenu,
  Flex,
  IconButton,
  ScrollArea,
  Text,
} from "@radix-ui/themes";
import axios from "axios";
import { ArrowUpDown, CheckCircle2, FileClock, XCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { ConfirmDialog, Spinner, StreamingMarkdown, toast } from "@/components";
import { ProjectNavItemRow } from "@/features/project-navigation/components/project-nav-item-row";
import { ProjectNavSearch } from "@/features/project-navigation/components/project-nav-search";
import { ProjectNavShell } from "@/features/project-navigation/components/project-nav-shell";
import { ProjectNavToolbar } from "@/features/project-navigation/components/project-nav-toolbar";
import { useAgentVisibilityCatalog } from "@/hooks/use-agent-visibility-catalog";

import {
  useApplyPendingProjectChange,
  usePendingProjectChangeCount,
  usePendingProjectChanges,
  useRejectPendingProjectChange,
} from "../hooks";
import type { JsonValue, PendingProjectChange } from "../types";

import "./pending-project-changes-dialog.css";

const EMPTY_PENDING_PROJECT_CHANGES: PendingProjectChange[] = [];

function formatCreatedAt(value: string, locale: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "medium" }).format(date);
}

type ChangeRecord = { [key: string]: JsonValue };

function asRecord(value: JsonValue): ChangeRecord | null {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value : null;
}

function asString(value: JsonValue | undefined): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function getChangeRecord(
  change: PendingProjectChange,
  side: "before" | "after",
): ChangeRecord | null {
  return asRecord(change[side]);
}

function getMaterialKind(change: PendingProjectChange): string {
  const after = getChangeRecord(change, "after");
  const before = getChangeRecord(change, "before");
  const documentType = asString(after?.document_type) ?? asString(before?.document_type);
  if (change.target_type === "note") return documentType === "outline" ? "outline" : "note";
  if (change.target_type === "note_category") {
    return documentType === "outline" ? "outlineCategory" : "noteCategory";
  }
  if (change.target_type === "character") return "character";
  if (change.target_type === "world_entry") return "worldEntry";
  return "material";
}

function getChangeTitle(change: PendingProjectChange): string | null {
  return (
    asString(getChangeRecord(change, "after")?.title) ??
    asString(getChangeRecord(change, "before")?.title)
  );
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

function formatFieldValue(
  value: JsonValue | undefined,
  emptyLabel: string,
  visibleLabel: string,
  hiddenLabel: string,
): string {
  if (typeof value === "boolean") return value ? visibleLabel : hiddenLabel;
  if (typeof value === "string" && value.trim()) return value;
  return emptyLabel;
}

function FieldComparison({
  label,
  before,
  after,
  emptyLabel,
  visibleLabel,
  hiddenLabel,
}: {
  label: string;
  before: JsonValue | undefined;
  after: JsonValue | undefined;
  emptyLabel: string;
  visibleLabel: string;
  hiddenLabel: string;
}) {
  if (before === after) return null;
  return (
    <div className="pending-project-changes-field-comparison">
      <Text
        size="1"
        color="gray"
      >
        {label}
      </Text>
      <div className="pending-project-changes-field-values">
        <Text
          size="2"
          className="pending-project-changes-field-value pending-project-changes-field-value--before"
        >
          {formatFieldValue(before, emptyLabel, visibleLabel, hiddenLabel)}
        </Text>
        <span
          className="pending-project-changes-field-arrow"
          aria-hidden="true"
        >
          →
        </span>
        <Text
          size="2"
          className="pending-project-changes-field-value pending-project-changes-field-value--after"
        >
          {formatFieldValue(after, emptyLabel, visibleLabel, hiddenLabel)}
        </Text>
      </div>
    </div>
  );
}

function BodyComparison({
  before,
  after,
  label,
  beforeLabel,
  afterLabel,
  emptyLabel,
}: {
  before: string;
  after: string;
  label: string;
  beforeLabel: string;
  afterLabel: string;
  emptyLabel: string;
}) {
  return (
    <section className="pending-project-changes-content-section">
      <Text
        size="2"
        weight="medium"
      >
        {label}
      </Text>
      <div className="pending-project-changes-body-comparison">
        <article className="pending-project-changes-body-version">
          <Text
            size="2"
            weight="medium"
            className="pending-project-changes-body-version-header"
          >
            {beforeLabel}
          </Text>
          <Box className="pending-project-changes-body-version-content">
            {before ? (
              <StreamingMarkdown content={before} />
            ) : (
              <Text
                size="2"
                color="gray"
              >
                {emptyLabel}
              </Text>
            )}
          </Box>
        </article>
        <article className="pending-project-changes-body-version">
          <Text
            size="2"
            weight="medium"
            className="pending-project-changes-body-version-header"
          >
            {afterLabel}
          </Text>
          <Box className="pending-project-changes-body-version-content">
            {after ? (
              <StreamingMarkdown content={after} />
            ) : (
              <Text
                size="2"
                color="gray"
              >
                {emptyLabel}
              </Text>
            )}
          </Box>
        </article>
      </div>
    </section>
  );
}

function MaterialContent({
  label,
  record,
  emptyLabel,
}: {
  label: string;
  record: ChangeRecord;
  emptyLabel: string;
}) {
  const body = asString(record.body);
  return (
    <section className="pending-project-changes-content-section">
      <Text
        size="2"
        weight="medium"
      >
        {label}
      </Text>
      {body ? (
        <Box className="pending-project-changes-markdown">
          <StreamingMarkdown content={body} />
        </Box>
      ) : (
        <Text
          size="2"
          color="gray"
        >
          {emptyLabel}
        </Text>
      )}
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
  const { data: visibilityCatalog } = useAgentVisibilityCatalog();
  const visibilityLabel = (value: unknown) =>
    visibilityCatalog?.states.find((state) => state.value === value)?.label ??
    (typeof value === "string" ? value : "");
  const { t, i18n } = useTranslation();
  const [selectedChangeId, setSelectedChangeId] = useState<string | null>(null);
  const [changeToReject, setChangeToReject] = useState<PendingProjectChange | null>(null);
  const [changeToApply, setChangeToApply] = useState<PendingProjectChange | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchExpanded, setSearchExpanded] = useState(false);
  const [sortDirection, setSortDirection] = useState<"newest" | "oldest">("newest");
  const changesQuery = usePendingProjectChanges(projectId, "pending");
  const countQuery = usePendingProjectChangeCount(projectId);
  const rejectMutation = useRejectPendingProjectChange(projectId);
  const applyMutation = useApplyPendingProjectChange(projectId);
  const changes = changesQuery.data ?? EMPTY_PENDING_PROJECT_CHANGES;
  const displayedChanges = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLocaleLowerCase(i18n.language);
    return changes
      .filter((change) => {
        if (!normalizedQuery) return true;
        const title = getChangeTitle(change) ?? "";
        const material = t(`pendingProjectChanges.materialTypes.${getMaterialKind(change)}`);
        const operation = t(`pendingProjectChanges.operations.${change.operation}`);
        return `${title} ${material} ${operation}`
          .toLocaleLowerCase(i18n.language)
          .includes(normalizedQuery);
      })
      .sort((left, right) =>
        sortDirection === "newest"
          ? right.created_at.localeCompare(left.created_at)
          : left.created_at.localeCompare(right.created_at),
      );
  }, [changes, i18n.language, searchQuery, sortDirection, t]);
  const selectedChange = useMemo(
    () =>
      displayedChanges.find((change) => change.id === selectedChangeId) ??
      displayedChanges[0] ??
      null,
    [displayedChanges, selectedChangeId],
  );

  useEffect(() => {
    if (!displayedChanges.length) {
      setSelectedChangeId(null);
    } else if (!displayedChanges.some((change) => change.id === selectedChangeId)) {
      setSelectedChangeId(displayedChanges[0].id);
    }
  }, [displayedChanges, selectedChangeId]);

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
  const selectedBefore = selectedChange ? getChangeRecord(selectedChange, "before") : null;
  const selectedAfter = selectedChange ? getChangeRecord(selectedChange, "after") : null;
  const selectedMaterialKind = selectedChange ? getMaterialKind(selectedChange) : "material";
  const selectedMaterialLabel = t(`pendingProjectChanges.materialTypes.${selectedMaterialKind}`);
  const selectedOperationLabel = selectedChange
    ? t(`pendingProjectChanges.operations.${selectedChange.operation}`)
    : "";
  const selectedTitle = selectedChange ? getChangeTitle(selectedChange) : null;
  const selectedHeading = selectedTitle
    ? t("pendingProjectChanges.changeHeading", {
        operation: selectedOperationLabel,
        material: selectedMaterialLabel,
        title: selectedTitle,
      })
    : t("pendingProjectChanges.changeHeadingWithoutTitle", {
        operation: selectedOperationLabel,
        material: selectedMaterialLabel,
      });
  const hasSelectedFieldChanges = Boolean(
    selectedBefore &&
    selectedAfter &&
    (selectedBefore.title !== selectedAfter.title ||
      selectedBefore.agent_visibility !== selectedAfter.agent_visibility ||
      selectedBefore.section !== selectedAfter.section),
  );
  const hasSelectedBodyChange = Boolean(
    selectedBefore &&
    selectedAfter &&
    asString(selectedBefore.body) !== asString(selectedAfter.body),
  );

  return (
    <>
      <div className={panelClassName}>
        {
          <div className="pending-project-changes-layout">
            <ProjectNavShell>
              <ProjectNavToolbar
                searchExpanded={searchExpanded}
                search={
                  <Flex
                    align="center"
                    gap="2"
                  >
                    <ProjectNavSearch
                      onExpandedChange={setSearchExpanded}
                      value={searchQuery}
                      onChange={setSearchQuery}
                      placeholder={t("pendingProjectChanges.searchPlaceholder")}
                    />
                    <Badge
                      color="amber"
                      variant="soft"
                    >
                      {pendingCount}
                    </Badge>
                  </Flex>
                }
                sort={
                  <DropdownMenu.Root>
                    <DropdownMenu.Trigger>
                      <IconButton
                        variant="ghost"
                        size="2"
                        aria-label={t("pendingProjectChanges.sort")}
                      >
                        <ArrowUpDown size={16} />
                      </IconButton>
                    </DropdownMenu.Trigger>
                    <DropdownMenu.Content align="end">
                      <DropdownMenu.CheckboxItem
                        checked={sortDirection === "newest"}
                        onCheckedChange={() => setSortDirection("newest")}
                      >
                        {t("pendingProjectChanges.sortNewest")}
                      </DropdownMenu.CheckboxItem>
                      <DropdownMenu.CheckboxItem
                        checked={sortDirection === "oldest"}
                        onCheckedChange={() => setSortDirection("oldest")}
                      >
                        {t("pendingProjectChanges.sortOldest")}
                      </DropdownMenu.CheckboxItem>
                    </DropdownMenu.Content>
                  </DropdownMenu.Root>
                }
              />
              <ScrollArea className="pending-project-changes-list-scroll">
                <div className="pending-project-changes-list">
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
                            getErrorMessage(changesQuery.error) ||
                            t("pendingProjectChanges.unknownError"),
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
                  ) : displayedChanges.length === 0 ? (
                    <Text
                      size="2"
                      color="gray"
                      align="center"
                      as="div"
                      style={{ padding: "var(--space-4)" }}
                    >
                      {t(
                        changes.length
                          ? "pendingProjectChanges.noSearchResults"
                          : "pendingProjectChanges.empty",
                      )}
                    </Text>
                  ) : (
                    displayedChanges.map((change) => (
                      <ProjectNavItemRow
                        key={change.id}
                        role="button"
                        tabIndex={0}
                        selected={change.id === selectedChange?.id}
                        onClick={() => setSelectedChangeId(change.id)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            setSelectedChangeId(change.id);
                          }
                        }}
                        title={
                          getChangeTitle(change)
                            ? t("pendingProjectChanges.changeHeading", {
                                operation: t(
                                  `pendingProjectChanges.operations.${change.operation}`,
                                ),
                                material: t(
                                  `pendingProjectChanges.materialTypes.${getMaterialKind(change)}`,
                                ),
                                title: getChangeTitle(change),
                              })
                            : t("pendingProjectChanges.changeHeadingWithoutTitle", {
                                operation: t(
                                  `pendingProjectChanges.operations.${change.operation}`,
                                ),
                                material: t(
                                  `pendingProjectChanges.materialTypes.${getMaterialKind(change)}`,
                                ),
                              })
                        }
                        metadata={formatCreatedAt(change.created_at, i18n.language)}
                        actions={
                          <Badge
                            color="amber"
                            variant="soft"
                          >
                            {t("pendingProjectChanges.navStatus")}
                          </Badge>
                        }
                      />
                    ))
                  )}
                </div>
              </ScrollArea>
            </ProjectNavShell>
            {selectedChange ? (
              <div className="pending-project-changes-detail-scroll">
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
                      {selectedHeading}
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
                      value={selectedMaterialLabel}
                    />
                    <ChangeMetadata
                      label={t("pendingProjectChanges.operation")}
                      value={selectedOperationLabel}
                    />
                    <ChangeMetadata
                      label={t("pendingProjectChanges.createdAt")}
                      value={formatCreatedAt(selectedChange.created_at, i18n.language)}
                    />
                    {selectedChange.operation !== "update" &&
                    selectedAfter &&
                    typeof selectedAfter.agent_visibility === "string" ? (
                      <ChangeMetadata
                        label="资料可见性"
                        value={visibilityLabel(selectedAfter.agent_visibility)}
                      />
                    ) : null}
                    {selectedChange.operation !== "update" && asString(selectedAfter?.section) ? (
                      <ChangeMetadata
                        label={t("pendingProjectChanges.section")}
                        value={asString(selectedAfter?.section) ?? ""}
                      />
                    ) : null}
                  </div>
                  <div className="pending-project-changes-review-content">
                    {selectedChange.operation === "update" &&
                    selectedBefore &&
                    selectedAfter &&
                    hasSelectedFieldChanges ? (
                      <section className="pending-project-changes-field-changes">
                        <Text
                          size="2"
                          weight="medium"
                        >
                          {t("pendingProjectChanges.changedFields")}
                        </Text>
                        <FieldComparison
                          label={t("pendingProjectChanges.titleField")}
                          before={selectedBefore.title}
                          after={selectedAfter.title}
                          emptyLabel={t("pendingProjectChanges.none")}
                          visibleLabel={t("pendingProjectChanges.visibleToWritingAgent")}
                          hiddenLabel={t("pendingProjectChanges.hiddenFromWritingAgent")}
                        />
                        <FieldComparison
                          label="资料可见性"
                          before={visibilityLabel(selectedBefore.agent_visibility)}
                          after={visibilityLabel(selectedAfter.agent_visibility)}
                          emptyLabel={t("pendingProjectChanges.none")}
                          visibleLabel={t("pendingProjectChanges.visibleToWritingAgent")}
                          hiddenLabel={t("pendingProjectChanges.hiddenFromWritingAgent")}
                        />
                        <FieldComparison
                          label={t("pendingProjectChanges.section")}
                          before={selectedBefore.section}
                          after={selectedAfter.section}
                          emptyLabel={t("pendingProjectChanges.none")}
                          visibleLabel={t("pendingProjectChanges.visibleToWritingAgent")}
                          hiddenLabel={t("pendingProjectChanges.hiddenFromWritingAgent")}
                        />
                      </section>
                    ) : null}
                    {selectedChange.operation === "update" &&
                    selectedBefore &&
                    selectedAfter &&
                    hasSelectedBodyChange ? (
                      <BodyComparison
                        label={t("pendingProjectChanges.bodyDiff")}
                        before={asString(selectedBefore.body) ?? ""}
                        after={asString(selectedAfter.body) ?? ""}
                        beforeLabel={t("pendingProjectChanges.before")}
                        afterLabel={t("pendingProjectChanges.proposedVersion")}
                        emptyLabel={t("pendingProjectChanges.noBody")}
                      />
                    ) : null}
                    {selectedChange.operation === "create" && selectedAfter ? (
                      <MaterialContent
                        label={t("pendingProjectChanges.proposedContent")}
                        record={selectedAfter}
                        emptyLabel={t("pendingProjectChanges.noBody")}
                      />
                    ) : null}
                    {selectedChange.operation === "delete" && selectedBefore ? (
                      <MaterialContent
                        label={t("pendingProjectChanges.contentToDelete")}
                        record={selectedBefore}
                        emptyLabel={t("pendingProjectChanges.noBody")}
                      />
                    ) : null}
                  </div>
                  <details className="pending-project-changes-technical-details">
                    <summary>{t("pendingProjectChanges.technicalDetails")}</summary>
                    <div className="pending-project-changes-metadata">
                      <ChangeMetadata
                        label={t("pendingProjectChanges.targetId")}
                        value={selectedChange.target_id ?? t("pendingProjectChanges.none")}
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
                  </details>
                </div>
              </div>
            ) : (
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
                  {t(
                    changes.length
                      ? "pendingProjectChanges.noSearchResults"
                      : "pendingProjectChanges.empty",
                  )}
                </Text>
              </Flex>
            )}
          </div>
        }
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
