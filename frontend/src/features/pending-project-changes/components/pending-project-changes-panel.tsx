import "./pending-project-changes-panel.css";
import {
  Badge,
  Box,
  Button,
  DropdownMenu,
  Flex,
  IconButton,
  ScrollArea,
  Select,
  Text,
  TextArea,
} from "@radix-ui/themes";
import axios from "axios";
import { ArrowUpDown, CheckCircle2, FileClock, Pencil, RefreshCw, XCircle } from "lucide-react";
import { type ReactNode, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";

import { ConfirmDialog, Spinner, toast } from "@/components";
import { ProjectNavItemRow } from "@/features/project-navigation/components/project-nav-item-row";
import { ProjectNavSearch } from "@/features/project-navigation/components/project-nav-search";
import { ProjectNavShell } from "@/features/project-navigation/components/project-nav-shell";
import { ProjectNavToolbar } from "@/features/project-navigation/components/project-nav-toolbar";
import { useAgentVisibilityCatalog } from "@/hooks/use-agent-visibility-catalog";

import { getPendingProjectChangeRevision } from "../api";
import {
  useApplyPendingProjectChange,
  usePendingProjectChange,
  usePendingProjectChangeCount,
  usePendingProjectChangeRevision,
  usePendingProjectChangeRevisions,
  usePendingProjectChanges,
  useRefreshPendingProjectChanges,
  useRejectPendingProjectChange,
  useRevisePendingProjectChange,
} from "../hooks";
import type { JsonValue, PendingProjectChange, PendingProjectChangeRevision } from "../types";
import { compareBodyDetails } from "./body-diff";
import { BodyDiffLegend, BodyDiffMarkdown } from "./body-diff-markdown";
import { PendingChangeFields } from "./pending-change-fields";
import { useComparisonScroll } from "./use-comparison-scroll";

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
  afterEditor,
}: {
  afterEditor?: ReactNode;
  before: string;
  after: string;
  label: string;
  beforeLabel: string;
  afterLabel: ReactNode;
  emptyLabel: string;
}) {
  const changes = useMemo(() => compareBodyDetails(before, after), [before, after]);
  return (
    <section className="pending-project-changes-content-section">
      <Text
        size="2"
        weight="medium"
      >
        {label}
      </Text>
      <BodyDiffLegend />
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
              <BodyDiffMarkdown
                content={before}
                changes={changes.before}
                ranges={changes.beforeRanges}
                side="before"
              />
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
            as="div"
            size="2"
            weight="medium"
            className="pending-project-changes-body-version-header"
          >
            {afterLabel}
          </Text>
          <Box className="pending-project-changes-body-version-content">
            {afterEditor ??
              (after ? (
                <BodyDiffMarkdown
                  content={after}
                  changes={changes.after}
                  ranges={changes.afterRanges}
                  side="after"
                />
              ) : (
                <Text
                  size="2"
                  color="gray"
                >
                  {emptyLabel}
                </Text>
              ))}
          </Box>
        </article>
      </div>
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
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedChangeId = searchParams.get("change");
  const [draft, setDraft] = useState<{
    change: PendingProjectChange;
    values: Record<string, string>;
  } | null>(null);
  const [switchTo, setSwitchTo] = useState<{ id: string | null } | null>(null);
  const setSelectedChangeId = (id: string | null) => {
    if (reviseMutation.isPending || preparingApply) return;
    if (draft && id !== draft.change.id) {
      setSwitchTo({ id });
      return;
    }
    setSearchParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        if (id) next.set("change", id);
        else next.delete("change");
        return next;
      },
      { replace: true },
    );
  };
  const [changeToReject, setChangeToReject] = useState<PendingProjectChange | null>(null);
  const [changeToApply, setChangeToApply] = useState<{
    change: PendingProjectChange;
    revision: PendingProjectChangeRevision;
    versionLabel: string;
  } | null>(null);
  const [revisionSelection, setRevisionSelection] = useState<{
    changeId: string;
    revisionId: string;
  } | null>(null);
  const [preparingApply, setPreparingApply] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchExpanded, setSearchExpanded] = useState(false);
  const [sortDirection, setSortDirection] = useState<"newest" | "oldest">("newest");
  const changesQuery = usePendingProjectChanges(projectId, "pending");
  const countQuery = usePendingProjectChangeCount(projectId);
  const rejectMutation = useRejectPendingProjectChange(projectId);
  const applyMutation = useApplyPendingProjectChange(projectId);
  const reviseMutation = useRevisePendingProjectChange(projectId);
  const refresh = useRefreshPendingProjectChanges(projectId);
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
  const listedChange = useMemo(
    () =>
      draft
        ? (changes.find((change) => change.id === draft.change.id) ?? null)
        : selectedChangeId
          ? (displayedChanges.find((change) => change.id === selectedChangeId) ?? null)
          : (displayedChanges[0] ?? null),
    [changes, displayedChanges, selectedChangeId, draft],
  );
  const activeChangeId = draft?.change.id ?? listedChange?.id ?? selectedChangeId;
  const detailQuery = usePendingProjectChange(projectId, activeChangeId);
  const selectedChange =
    detailQuery.data && (!listedChange || detailQuery.dataUpdatedAt >= changesQuery.dataUpdatedAt)
      ? detailQuery.data
      : (listedChange ?? draft?.change ?? null);
  const revisionsQuery = usePendingProjectChangeRevisions(projectId, selectedChange?.id ?? null);
  const selectedRevisionId =
    revisionSelection && revisionSelection.changeId === selectedChange?.id
      ? revisionSelection.revisionId
      : null;
  const revisionQuery = usePendingProjectChangeRevision(
    projectId,
    selectedChange?.id ?? null,
    selectedRevisionId,
  );
  const revisions = useMemo(
    () => [...(revisionsQuery.data ?? [])].sort((a, b) => a.created_at.localeCompare(b.created_at)),
    [revisionsQuery.data],
  );
  const versionLabel = (revisionId: string) => {
    const index = revisions.findIndex((revision) => revision.id === revisionId);
    return t("pendingProjectChanges.revisionVersion", {
      version: index < 0 ? revisionId : index + 1,
    });
  };
  const viewedRevisionId = selectedRevisionId ?? selectedChange?.current_revision_id;
  const latestRevision = revisions.find(
    (revision) => revision.id === selectedChange?.current_revision_id,
  );
  const viewedRevision = selectedRevisionId ? revisionQuery.data : latestRevision;
  const historical = Boolean(
    selectedRevisionId && selectedRevisionId !== selectedChange?.current_revision_id,
  );
  const reviewReady = !selectedRevisionId || Boolean(revisionQuery.data);
  const busy = preparingApply || applyMutation.isPending || rejectMutation.isPending;

  const comparisonRef = useComparisonScroll(selectedChange?.id);
  const updateDraft = (key: string, value: string) =>
    setDraft((current) =>
      current ? { ...current, values: { ...current.values, [key]: value } } : null,
    );
  const startEditing = () => {
    if (!selectedChange) return;
    if (selectedChange.status !== "pending") return;
    // Historical snapshots are immutable. Editing always starts at the latest head.
    setRevisionSelection(null);
    const after = getChangeRecord(selectedChange, "after") ?? {};
    const keys =
      selectedChange.target_type === "note_category"
        ? ["title"]
        : [
            "title",
            "body",
            "agent_visibility",
            ...(selectedChange.target_type === "world_entry" ? ["section"] : []),
          ];
    setDraft({
      change: selectedChange,
      values: Object.fromEntries(
        keys.map((key) => [key, typeof after[key] === "string" ? after[key] : ""]),
      ),
    });
  };
  const refreshReview = async () => {
    setRefreshing(true);
    try {
      await refresh();
    } finally {
      setRefreshing(false);
    }
  };
  const saveDraft = () => {
    if (!draft) return;
    const after = getChangeRecord(draft.change, "after") ?? {};
    const patch = Object.fromEntries(
      Object.entries(draft.values).filter(([key, value]) => value !== after[key]),
    );
    if (!Object.keys(patch).length) {
      setDraft(null);
      return;
    }
    reviseMutation.mutate(
      { change: draft.change, patch },
      {
        onSuccess: () => {
          setDraft(null);
          toast.success(t("pendingProjectChanges.reviseSuccess"));
        },
        onError: (error) => {
          if (axios.isAxiosError(error) && error.response?.status === 409) void refresh();
          toast.error(
            axios.isAxiosError(error) && error.response?.status === 409
              ? t("pendingProjectChanges.reviseConflict")
              : t("pendingProjectChanges.reviseFailed", { error: getErrorMessage(error) }),
          );
        },
      },
    );
  };

  const prepareApply = async () => {
    if (!selectedChange?.current_revision_id || !viewedRevisionId || !reviewReady || draft || busy)
      return;
    const displayed = selectedChange;
    const revisionId = viewedRevisionId;
    const label = versionLabel(revisionId);
    setPreparingApply(true);
    try {
      const [freshResult, revision] = await Promise.all([
        detailQuery.refetch(),
        getPendingProjectChangeRevision(projectId, displayed.id, revisionId),
      ]);
      if (freshResult.error) throw freshResult.error;
      const fresh = freshResult.data;
      if (!fresh || fresh.status !== "pending") {
        toast.error(t("pendingProjectChanges.selectionUnavailable"));
        void refresh();
        return;
      }
      if (
        fresh.updated_at !== displayed.updated_at ||
        fresh.current_hash !== displayed.current_hash ||
        fresh.current_revision_id !== displayed.current_revision_id ||
        JSON.stringify(revision.after) !==
          JSON.stringify(selectedRevisionId ? revisionQuery.data?.after : displayed.after)
      ) {
        toast.info(t("pendingProjectChanges.reviewRefreshed"));
        void refresh();
        return;
      }
      if (!fresh.is_applicable) {
        toast.error(fresh.applicability_reason ?? t("pendingProjectChanges.notApplicable"));
        return;
      }
      setChangeToApply({ change: fresh, revision, versionLabel: label });
    } catch (error) {
      toast.error(
        t("pendingProjectChanges.loadFailed", {
          error: getErrorMessage(error) || t("pendingProjectChanges.unknownError"),
        }),
      );
    } finally {
      setPreparingApply(false);
    }
  };

  const handleReject = () => {
    if (!changeToReject) return;
    rejectMutation.mutate(changeToReject, {
      onSuccess: () => {
        toast.success(t("pendingProjectChanges.rejectSuccess"));
        setSelectedChangeId(null);
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
    const { change, revision } = changeToApply;
    applyMutation.mutate(
      {
        change,
        request: {
          expected_updated_at: change.updated_at,
          expected_current_hash: change.current_hash,
          revision_id: revision.id,
        },
      },
      {
        onSuccess: () => {
          toast.success(t("pendingProjectChanges.applySuccess"));
          setSelectedChangeId(null);
          setChangeToApply(null);
        },
        onError: (error) => {
          if (axios.isAxiosError(error) && error.response?.status === 409) {
            setChangeToApply(null);
            void refresh();
            toast.error(t("pendingProjectChanges.applyConflict"));
            return;
          }
          toast.error(
            t("pendingProjectChanges.applyFailed", {
              error: getErrorMessage(error) || t("pendingProjectChanges.unknownError"),
            }),
          );
        },
      },
    );
  };

  const pendingCount = countQuery.data?.count ?? 0;
  const panelClassName = ["pending-project-changes-panel", className].filter(Boolean).join(" ");
  const selectedBefore = selectedChange ? asRecord(selectedChange.current) : null;
  const selectedAfter = draft
    ? { ...getChangeRecord(draft.change, "after"), ...draft.values }
    : selectedRevisionId
      ? asRecord(revisionQuery.data?.after ?? null)
      : selectedChange
        ? getChangeRecord(selectedChange, "after")
        : null;
  const selectedMaterialKind = selectedChange ? getMaterialKind(selectedChange) : "material";
  const selectedMaterialLabel = t(`pendingProjectChanges.materialTypes.${selectedMaterialKind}`);
  const selectedOperationLabel = selectedChange
    ? t(`pendingProjectChanges.operations.${selectedChange.operation}`)
    : "";
  const selectedTitle = asString(selectedAfter?.title) ?? asString(selectedBefore?.title);
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
  const hasSelectedFieldChanges =
    selectedBefore?.title !== selectedAfter?.title ||
    selectedBefore?.agent_visibility !== selectedAfter?.agent_visibility ||
    selectedBefore?.section !== selectedAfter?.section;
  const hasSelectedBodyChange = Boolean(
    selectedBefore &&
    selectedAfter &&
    asString(selectedBefore.body) !== asString(selectedAfter.body),
  );
  const revisionSelector = (
    <Flex
      align="center"
      justify="between"
      gap="2"
      wrap="wrap"
    >
      <Text
        size="2"
        weight="medium"
      >
        {t("pendingProjectChanges.proposedVersion")}
      </Text>
      <Select.Root
        size="1"
        value={selectedRevisionId ?? "latest"}
        disabled={Boolean(draft) || busy}
        onValueChange={(revisionId) =>
          setRevisionSelection(
            revisionId === "latest" || !selectedChange
              ? null
              : { changeId: selectedChange.id, revisionId },
          )
        }
      >
        <Select.Trigger aria-label={t("pendingProjectChanges.revisionHistory")}>
          {selectedRevisionId
            ? versionLabel(selectedRevisionId)
            : t("pendingProjectChanges.latestRevision")}
        </Select.Trigger>
        <Select.Content position="popper">
          <Select.Item value="latest">
            {t("pendingProjectChanges.latestRevision")}
            {latestRevision && (
              <>
                {" "}
                · {t(`pendingProjectChanges.revisionSources.${latestRevision.source}`)} ·{" "}
                {formatCreatedAt(latestRevision.created_at, i18n.language)}
              </>
            )}
          </Select.Item>
          {revisions.map((revision) => (
            <Select.Item
              key={revision.id}
              value={revision.id}
            >
              {versionLabel(revision.id)} ·{" "}
              {t(`pendingProjectChanges.revisionSources.${revision.source}`)} ·{" "}
              {formatCreatedAt(revision.created_at, i18n.language)}
            </Select.Item>
          ))}
        </Select.Content>
      </Select.Root>
    </Flex>
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
                      className="pending-project-changes-panel__details"
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
              <div
                className="pending-project-changes-detail-scroll"
                ref={comparisonRef}
                key={selectedChange.id}
              >
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
                    <Flex
                      gap="2"
                      wrap="wrap"
                    >
                      <IconButton
                        size="1"
                        variant="soft"
                        aria-label={t("pendingProjectChanges.refresh")}
                        title={t("pendingProjectChanges.refresh")}
                        disabled={busy || reviseMutation.isPending}
                        loading={refreshing}
                        onClick={() => void refreshReview()}
                      >
                        <RefreshCw size={14} />
                      </IconButton>
                      {draft ? (
                        <>
                          <Button
                            size="1"
                            onClick={saveDraft}
                            loading={reviseMutation.isPending}
                            disabled={!draft.values.title.trim()}
                          >
                            {t("pendingProjectChanges.saveDraft")}
                          </Button>
                          <Button
                            size="1"
                            variant="soft"
                            disabled={reviseMutation.isPending}
                            onClick={() => setDraft(null)}
                          >
                            {t("common.cancel")}
                          </Button>
                        </>
                      ) : (
                        selectedChange.operation !== "delete" && (
                          <Button
                            size="1"
                            variant="soft"
                            onClick={startEditing}
                            disabled={busy || selectedChange.status !== "pending"}
                          >
                            <Pencil size={14} />
                            {t("pendingProjectChanges.editDraft")}
                          </Button>
                        )
                      )}
                      {selectedChange.is_applicable && selectedChange.status === "pending" ? (
                        <Button
                          size="1"
                          color="green"
                          onClick={() => void prepareApply()}
                          loading={preparingApply || applyMutation.isPending}
                          disabled={
                            rejectMutation.isPending ||
                            Boolean(draft) ||
                            !reviewReady ||
                            !viewedRevisionId ||
                            !selectedChange.current_revision_id ||
                            !revisionsQuery.data ||
                            revisionsQuery.isError ||
                            revisionQuery.isError ||
                            detailQuery.isError
                          }
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
                        disabled={busy || Boolean(draft) || selectedChange.status !== "pending"}
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
                  {!selectedChange.is_applicable && selectedChange.applicability_reason && (
                    <Text
                      size="2"
                      color="amber"
                      role="status"
                    >
                      {selectedChange.applicability_reason}
                    </Text>
                  )}
                  {historical && !draft && (
                    <Text
                      size="1"
                      color="gray"
                      role="status"
                    >
                      {t("pendingProjectChanges.historicalReadOnly", {
                        version: versionLabel(selectedRevisionId!),
                      })}
                    </Text>
                  )}
                  {draft && draft.change.updated_at !== selectedChange.updated_at && (
                    <Text
                      size="1"
                      color="amber"
                      role="status"
                    >
                      {t("pendingProjectChanges.reviseConflict")}
                    </Text>
                  )}
                  {(revisionsQuery.isError || revisionQuery.isError || detailQuery.isError) && (
                    <Flex
                      align="center"
                      gap="2"
                    >
                      <Text
                        size="1"
                        color="red"
                        role="alert"
                      >
                        {t("pendingProjectChanges.historyLoadFailed")}
                      </Text>
                      <Button
                        size="1"
                        variant="soft"
                        onClick={() => void refreshReview()}
                      >
                        {t("pendingProjectChanges.retry")}
                      </Button>
                    </Flex>
                  )}
                  {draft && (
                    <>
                      <Text
                        size="1"
                        color="gray"
                      >
                        {t("pendingProjectChanges.editHint")}
                      </Text>
                      <PendingChangeFields
                        targetType={selectedChange.target_type}
                        values={draft.values}
                        onChange={updateDraft}
                        disabled={reviseMutation.isPending}
                      />
                    </>
                  )}
                  <div className="pending-project-changes-review-content">
                    {selectedChange.target_type === "note_category" && revisionSelector}
                    {!reviewReady && (
                      <Text
                        size="2"
                        color="gray"
                        role="status"
                      >
                        {t("pendingProjectChanges.loadingRevision")}
                      </Text>
                    )}
                    {selectedChange.operation === "update" &&
                    selectedBefore &&
                    selectedAfter &&
                    !hasSelectedFieldChanges &&
                    !hasSelectedBodyChange &&
                    !draft ? (
                      <Text
                        size="2"
                        color="gray"
                        role="status"
                      >
                        {t("pendingProjectChanges.noChanges")}
                      </Text>
                    ) : null}
                    {reviewReady && hasSelectedFieldChanges && !draft ? (
                      <section className="pending-project-changes-field-changes">
                        <Text
                          size="2"
                          weight="medium"
                        >
                          {t("pendingProjectChanges.changedFields")}
                        </Text>
                        <FieldComparison
                          label={t("pendingProjectChanges.titleField")}
                          before={selectedBefore?.title}
                          after={selectedAfter?.title}
                          emptyLabel={t("pendingProjectChanges.none")}
                          visibleLabel={t("pendingProjectChanges.visibleToWritingAgent")}
                          hiddenLabel={t("pendingProjectChanges.hiddenFromWritingAgent")}
                        />
                        <FieldComparison
                          label={t("pendingProjectChanges.visibilityField")}
                          before={visibilityLabel(selectedBefore?.agent_visibility)}
                          after={visibilityLabel(selectedAfter?.agent_visibility)}
                          emptyLabel={t("pendingProjectChanges.none")}
                          visibleLabel={t("pendingProjectChanges.visibleToWritingAgent")}
                          hiddenLabel={t("pendingProjectChanges.hiddenFromWritingAgent")}
                        />
                        <FieldComparison
                          label={t("pendingProjectChanges.section")}
                          before={selectedBefore?.section}
                          after={selectedAfter?.section}
                          emptyLabel={t("pendingProjectChanges.none")}
                          visibleLabel={t("pendingProjectChanges.visibleToWritingAgent")}
                          hiddenLabel={t("pendingProjectChanges.hiddenFromWritingAgent")}
                        />
                      </section>
                    ) : null}
                    {selectedChange.target_type !== "note_category" ? (
                      <BodyComparison
                        label={t(
                          selectedChange.operation === "delete"
                            ? "pendingProjectChanges.contentToDelete"
                            : "pendingProjectChanges.bodyDiff",
                        )}
                        before={asString(selectedBefore?.body) ?? ""}
                        after={asString((reviewReady ? selectedAfter : selectedBefore)?.body) ?? ""}
                        afterEditor={
                          !reviewReady ? (
                            <Text
                              size="2"
                              color="gray"
                              role="status"
                            >
                              {t("pendingProjectChanges.loadingRevision")}
                            </Text>
                          ) : draft && selectedChange.target_type !== "note_category" ? (
                            <TextArea
                              className="pending-change-body-editor"
                              aria-label={t("pendingProjectChanges.editBody")}
                              value={draft.values.body}
                              disabled={reviseMutation.isPending}
                              onChange={(event) => updateDraft("body", event.target.value)}
                            />
                          ) : undefined
                        }
                        beforeLabel={t("pendingProjectChanges.before")}
                        afterLabel={revisionSelector}
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
                        label={t("pendingProjectChanges.revisionSource")}
                        value={
                          viewedRevision
                            ? t(`pendingProjectChanges.revisionSources.${viewedRevision.source}`)
                            : t("pendingProjectChanges.none")
                        }
                      />
                      <ChangeMetadata
                        label={t("pendingProjectChanges.model")}
                        value={viewedRevision?.model_id ?? t("pendingProjectChanges.none")}
                      />
                      <ChangeMetadata
                        label={t("pendingProjectChanges.sourceTask")}
                        value={viewedRevision?.source_task_id ?? t("pendingProjectChanges.none")}
                      />
                      <ChangeMetadata
                        label={t("pendingProjectChanges.sourceMessage")}
                        value={viewedRevision?.source_message_id ?? t("pendingProjectChanges.none")}
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
                    changesQuery.isLoading
                      ? "pendingProjectChanges.loading"
                      : selectedChangeId && !searchQuery
                        ? "pendingProjectChanges.selectionUnavailable"
                        : changes.length
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
        open={Boolean(switchTo)}
        onOpenChange={(open) => {
          if (!open) setSwitchTo(null);
        }}
        title={t("pendingProjectChanges.discardTitle")}
        description={t("pendingProjectChanges.discardDescription")}
        confirmText={t("pendingProjectChanges.discard")}
        cancelText={t("common.cancel")}
        onConfirm={() => {
          const id = switchTo?.id;
          setDraft(null);
          setSwitchTo(null);
          setSearchParams(
            (previous) => {
              const next = new URLSearchParams(previous);
              if (id) next.set("change", id);
              else next.delete("change");
              return next;
            },
            { replace: true },
          );
        }}
      />
      <ConfirmDialog
        open={Boolean(changeToApply)}
        onOpenChange={(nextOpen) => {
          if (!nextOpen && !applyMutation.isPending) setChangeToApply(null);
        }}
        onConfirm={handleApply}
        title={t("pendingProjectChanges.applyConfirmTitle")}
        description={t(
          changeToApply?.change.operation === "delete"
            ? "pendingProjectChanges.applyDeleteConfirmDescription"
            : "pendingProjectChanges.applyConfirmDescription",
          { version: changeToApply?.versionLabel ?? "" },
        )}
        confirmText={t("pendingProjectChanges.apply")}
        confirmColor={changeToApply?.change.operation === "delete" ? "red" : "green"}
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
