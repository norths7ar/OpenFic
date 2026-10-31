import { Box, Button, Flex, IconButton, Text, Tooltip } from "@radix-ui/themes";
import { ArrowUp, CloudUpload, ExternalLink, ShieldCheck, Square, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { PhotoProvider, PhotoView } from "react-photo-view";

import "react-photo-view/dist/react-photo-view.css";
import "./agent-input.css";

import { ModelIdSelect, Spinner, type ModelIdSelectOption } from "@/components";
import { toast } from "@/components";
import { ModelDiscoveryStatus } from "@/components/model-discovery-status";
import { SimpleSelect, type SelectOption } from "@/components/select";
import { ProviderIcon } from "@/features/settings/lib/provider-icons";
import type { AgentPendingMessage, AgentSessionStatus, ReasoningEffort } from "@/lib/agent.types";

import { useAgentInputHistory } from "../../hooks/use-agent-input-history";
import {
  getAgentImageFiles,
  hasLeftAgentImageDropZone,
  modelAllowsAgentImages,
  type PendingAgentImageAttachment,
  validateAgentImageFiles,
} from "../../lib/agent-image-attachments";
import type { AgentInputHistoryDirection } from "../../lib/agent-input-history-state";
import { getMentionDisplayLabel, parseAssistantMarkup } from "../../lib/mention-text";
import { AgentComposerEditor, type AgentComposerSuggestionState } from "./agent-composer-editor";
import { AgentIndexStatusIndicator } from "./agent-index-status-indicator";
import { canSendAgentInput, getAgentInputBodyMode, isAgentInputLocked } from "./agent-input-state";
import { AgentMentionSuggestions } from "./agent-mention-suggestions";
import { DeliveryModeSelect } from "./delivery-mode-select";
import { MentionChip } from "./mention-chip";
import { AgentPendingMessageCard } from "./pending-message-card";

interface AgentInputProps {
  header?: ReactNode;
  projectId: string;
  value: string;
  submissionValue?: string;
  contextMode?: "global" | "local";
  automaticComposerMarkup?: string | null;
  onRemoveAutomaticComposerMarkup?: () => void;
  onHistoryRecallChange?: (recalled: boolean) => void;
  attachments: PendingAgentImageAttachment[];
  modelId: string;
  models: ModelIdSelectOption[];
  reasoningEffort?: ReasoningEffort;
  modelSpeed?: "standard" | "fast";
  onModelSpeedChange?: (speed: "standard" | "fast") => void;
  configurationError?: string;
  agentKey?: string;
  agentOptions: SelectOption[];
  agentChangeDisabled?: boolean;
  isSending: boolean;
  disabled: boolean;
  isModelsLoading: boolean;
  modelsError: boolean;
  onChange: (value: string) => void;
  onAttachmentsChange: (attachments: PendingAgentImageAttachment[]) => void;
  onSend: () => void;
  onAbort: () => void;
  onModelChange: (modelId: string) => void;
  onReasoningEffortChange?: (reasoningEffort: ReasoningEffort) => void;
  onAgentChange?: (agentKey: string) => void;
  onGoToSettings: () => void;
  agentStatus?: AgentSessionStatus;
  pendingMessages?: AgentPendingMessage[];
  deliveryMode?: "steer" | "queue";
  onDeliveryModeChange?: (mode: "steer" | "queue") => void;
  onOpenMentionChapter?: (chapterId: string, chapterTitle: string) => void;
  toolApprovalBypassEnabled?: boolean;
  toolApprovalBypassDisabled?: boolean;
  onToggleToolApprovalBypass?: () => void;
  onCancelPendingMessage?: (messageId?: string) => void;
  specialPanels?: ReactNode;
  forceSpecialPanels?: boolean;
  readOnly?: boolean;
  readOnlyMessage?: ReactNode;
  onUploadAttachments: (files: File[]) => Promise<void>;
  [ignoredModeSelectorProp: string]: unknown;
}

export function AgentInput({
  header,
  projectId,
  value,
  submissionValue = value,
  contextMode,
  automaticComposerMarkup = null,
  onRemoveAutomaticComposerMarkup,
  onHistoryRecallChange,
  attachments,
  modelId,
  models,
  reasoningEffort,
  modelSpeed = "standard",
  onModelSpeedChange,
  configurationError,
  agentKey,
  agentOptions,
  agentChangeDisabled = false,
  isSending,
  disabled,
  isModelsLoading,
  modelsError,
  onChange,
  onAttachmentsChange,
  onSend,
  onAbort,
  onModelChange,
  onReasoningEffortChange,
  onAgentChange,
  onGoToSettings,
  agentStatus,
  pendingMessages = [],
  deliveryMode = "steer",
  onDeliveryModeChange,
  onOpenMentionChapter,
  toolApprovalBypassEnabled = false,
  toolApprovalBypassDisabled = false,
  onToggleToolApprovalBypass,
  onCancelPendingMessage,
  specialPanels,
  forceSpecialPanels = false,
  readOnly = false,
  readOnlyMessage,
  onUploadAttachments,
}: AgentInputProps) {
  const { t } = useTranslation();
  const bodyMode = getAgentInputBodyMode(agentStatus, Boolean(specialPanels), forceSpecialPanels);
  const hasDraftContent = value.trim().length > 0 || attachments.length > 0;
  const hasContent = submissionValue.trim().length > 0 || attachments.length > 0;
  const hasPendingMessage = pendingMessages.length > 0;
  const isComposerLocked = isAgentInputLocked({
    disabled,
    readOnly,
  });
  const shouldAbort = isSending && !hasDraftContent;
  const canSend =
    !configurationError &&
    canSendAgentInput({
      hasContent,
      disabled,
      readOnly,
      bodyMode,
    });
  const shouldShowPendingMessage = hasPendingMessage && bodyMode === "composer" && !readOnly;
  const buttonActive = shouldAbort || canSend;
  const inputContainerRef = useRef<HTMLDivElement>(null);
  const [pendingClearanceHeight, setPendingClearanceHeight] = useState(0);
  const [mentionSuggestions, setMentionSuggestions] = useState<AgentComposerSuggestionState | null>(
    null,
  );
  const {
    draft: persistedDraft,
    handleInputChange: handleHistoryInputChange,
    historyState,
    isDraftLoaded,
    navigate: navigateInputHistory,
    record: recordInputHistory,
  } = useAgentInputHistory(projectId);
  const historyValueRef = useRef<string | null>(null);
  const restoredDraftProjectIdRef = useRef<string | null>(null);
  const previousProjectIdRef = useRef(projectId);
  const attachmentKey = attachments.map((attachment) => attachment.id).join(":");
  const previousAttachmentKeyRef = useRef(attachmentKey);
  const automaticMention = useMemo(
    () =>
      parseAssistantMarkup(automaticComposerMarkup ?? "").find(
        (segment) => typeof segment !== "string" && segment.markup === "mention",
      ),
    [automaticComposerMarkup],
  );
  const selectedModel = useMemo(
    () => models.find((model) => model.value === modelId || model.id === modelId),
    [modelId, models],
  );
  const [isDraggingImages, setIsDraggingImages] = useState(false);
  const canAttachImages = modelAllowsAgentImages(
    selectedModel?.inputModalities,
    selectedModel?.isCatalogMatched === true,
  );
  const modelTriggerPrefix = selectedModel ? (
    <ProviderIcon
      size={14}
      iconPath={selectedModel.providerIconPath}
    />
  ) : null;
  const speedCapability = selectedModel?.speedReasoningCapabilities?.[modelSpeed];
  const reasoningEffortStatus =
    speedCapability?.status ?? selectedModel?.reasoningEffortStatus ?? "unknown";
  const reasoningEffortLevels =
    reasoningEffortStatus === "supported"
      ? (speedCapability?.levels ?? selectedModel?.reasoningEffortLevels)
      : undefined;
  const getReasoningEffortLabel = (value: string) =>
    t(`assistant.reasoningEffort.${value}`, { defaultValue: value });
  const defaultReasoningEffort = speedCapability?.default ?? selectedModel?.reasoningEffortDefault;
  const defaultReasoningEffortLabel =
    reasoningEffortStatus === "supported" && defaultReasoningEffort
      ? t("assistant.reasoningEffortDefault", {
          level: getReasoningEffortLabel(defaultReasoningEffort),
        })
      : t("assistant.reasoningEffort.off");
  const reasoningEffortOptions: SelectOption[] = [
    { value: "off", label: defaultReasoningEffortLabel },
    ...[...new Set(reasoningEffortLevels ?? [])]
      .filter((value) => value !== "off")
      .map((value) => ({ value, label: getReasoningEffortLabel(value) })),
  ];
  const effectiveReasoningEffort = reasoningEffort ?? "off";
  if (!reasoningEffortOptions.some((option) => option.value === effectiveReasoningEffort)) {
    reasoningEffortOptions.push({
      value: effectiveReasoningEffort,
      label: getReasoningEffortLabel(effectiveReasoningEffort),
    });
  }

  useEffect(() => {
    if (previousProjectIdRef.current === projectId) return;
    previousProjectIdRef.current = projectId;
    historyValueRef.current = "";
    onHistoryRecallChange?.(false);
    onChange("");
  }, [onChange, onHistoryRecallChange, projectId]);

  useEffect(() => {
    if (!isDraftLoaded) return;
    if (restoredDraftProjectIdRef.current !== projectId) {
      restoredDraftProjectIdRef.current = projectId;
      if (persistedDraft && !value.trim()) {
        historyValueRef.current = persistedDraft;
        onChange(persistedDraft);
        return;
      }
    }
    if (historyValueRef.current === value) {
      historyValueRef.current = null;
      return;
    }
    historyValueRef.current = null;
    handleHistoryInputChange(value);
  }, [handleHistoryInputChange, isDraftLoaded, onChange, persistedDraft, projectId, value]);

  useEffect(() => {
    if (previousAttachmentKeyRef.current === attachmentKey) return;
    previousAttachmentKeyRef.current = attachmentKey;
    handleHistoryInputChange(value, true);
    onHistoryRecallChange?.(false);
  }, [attachmentKey, handleHistoryInputChange, onHistoryRecallChange, value]);

  const handleComposerChange = useCallback(
    (nextValue: string) => {
      historyValueRef.current = null;
      handleHistoryInputChange(nextValue);
      if (nextValue !== value) onHistoryRecallChange?.(false);
      onChange(nextValue);
    },
    [handleHistoryInputChange, onChange, onHistoryRecallChange, value],
  );

  const handleHistoryNavigate = useCallback(
    (direction: AgentInputHistoryDirection): boolean => {
      const result = navigateInputHistory(direction, value, attachments.length > 0);
      if (result === null) return false;
      historyValueRef.current = result.value;
      onHistoryRecallChange?.(result.isHistoryEntry);
      onChange(result.value);
      return true;
    },
    [attachments.length, navigateInputHistory, onChange, onHistoryRecallChange, value],
  );

  const handleSubmit = useCallback(() => {
    recordInputHistory(submissionValue);
    onSend();
  }, [onSend, recordInputHistory, submissionValue]);

  useLayoutEffect(() => {
    const container = inputContainerRef.current;
    if (!container) return;

    const syncHeight = () => {
      const nextHeight = Math.round(container.getBoundingClientRect().height);
      setPendingClearanceHeight((currentHeight) =>
        currentHeight === nextHeight ? currentHeight : nextHeight,
      );
    };

    syncHeight();

    if (typeof ResizeObserver === "undefined") return;

    const resizeObserver = new ResizeObserver(() => {
      syncHeight();
    });
    resizeObserver.observe(container);
    return () => {
      resizeObserver.disconnect();
    };
  }, []);

  useEffect(() => {
    if (bodyMode === "composer" && !readOnly && !isComposerLocked) return;
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      setMentionSuggestions(null);
    });
    return () => {
      cancelled = true;
    };
  }, [bodyMode, isComposerLocked, readOnly]);

  useEffect(() => {
    if (!isDraggingImages) return;

    const clearDraggingImages = () => setIsDraggingImages(false);
    window.addEventListener("dragend", clearDraggingImages);
    window.addEventListener("drop", clearDraggingImages);
    return () => {
      window.removeEventListener("dragend", clearDraggingImages);
      window.removeEventListener("drop", clearDraggingImages);
    };
  }, [isDraggingImages]);

  const getPlaceholder = () => {
    if (agentStatus === "waiting_answer")
      return t("writing.aiSidebar.inputPlaceholderWaitingAnswer");
    if (agentStatus === "waiting_approval")
      return t("writing.aiSidebar.inputPlaceholderWaitingApproval");
    return t("writing.aiSidebar.inputPlaceholder");
  };

  const handleFiles = async (files: File[]) => {
    const error = validateAgentImageFiles(files, attachments.length);
    if (error) {
      toast.error(error);
      return;
    }
    await onUploadAttachments(files);
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    const files = getAgentImageFiles(event.dataTransfer);
    if (files.length === 0) return;
    event.preventDefault();
    setIsDraggingImages(false);
    if (!canAttachImages) {
      toast.error(t("writing.aiSidebar.modelImageInputUnsupported"));
      return;
    }
    void handleFiles(files);
  };

  const handlePastedFiles = (dataTransfer: DataTransfer) => {
    const files = getAgentImageFiles(dataTransfer);
    if (files.length === 0) return;
    if (!canAttachImages) {
      toast.error(t("writing.aiSidebar.modelImageInputUnsupported"));
      return;
    }
    void handleFiles(files);
  };

  const handleDroppedFiles = (dataTransfer: DataTransfer) => {
    setIsDraggingImages(false);
    handlePastedFiles(dataTransfer);
  };

  const handleRemoveAttachment = (id: string) => {
    const attachment = attachments.find((item) => item.id === id);
    if (attachment) URL.revokeObjectURL(attachment.previewUrl);
    onAttachmentsChange(attachments.filter((item) => item.id !== id));
  };

  return (
    <Box className="ai-sidebar-input-area">
      {configurationError ? (
        <Text
          as="p"
          size="1"
          color="amber"
          role="status"
          mb="2"
        >
          {configurationError}
        </Text>
      ) : null}
      {selectedModel &&
      (selectedModel.upstreamStatus === "not_listed" ||
        selectedModel.discoveryStatus === "error") ? (
        <Flex
          align="center"
          justify="between"
          gap="2"
          mb="2"
          wrap="wrap"
        >
          <ModelDiscoveryStatus model={selectedModel} />
          <Button
            variant="ghost"
            size="1"
            onClick={onGoToSettings}
          >
            {t("models.reviewModels")}
          </Button>
        </Flex>
      ) : null}
      <div className="ai-sidebar-input-stage">
        <AnimatePresence initial={false}>
          {mentionSuggestions ? (
            <AgentMentionSuggestions
              key="mention-suggestions"
              clearanceHeight={pendingClearanceHeight}
              mode={mentionSuggestions.mode}
              items={mentionSuggestions.items}
              selectedIndex={mentionSuggestions.selectedIndex}
              status={mentionSuggestions.status}
              browser={mentionSuggestions.browser}
              visible
              onSelect={mentionSuggestions.onSelect}
              onSelectedIndexChange={mentionSuggestions.onSelectedIndexChange}
              onClose={mentionSuggestions.onClose}
            />
          ) : null}
        </AnimatePresence>

        <div className="ai-sidebar-pending-list">
          <AnimatePresence initial={false}>
            {shouldShowPendingMessage
              ? pendingMessages.map((pendingMessage) => (
                  <AgentPendingMessageCard
                    key={`pending-${pendingMessage.messageId}`}
                    pendingMessage={pendingMessage}
                    clearanceHeight={0}
                    onCancel={
                      onCancelPendingMessage
                        ? () => onCancelPendingMessage(pendingMessage.messageId)
                        : undefined
                    }
                    onOpenMentionChapter={onOpenMentionChapter}
                  />
                ))
              : null}
          </AnimatePresence>
        </div>

        <div
          ref={inputContainerRef}
          className="ai-sidebar-input-container"
          data-mode={bodyMode}
          data-dragging-images={isDraggingImages || undefined}
          onDragEnter={(event) => {
            if (event.dataTransfer.types.includes("Files")) setIsDraggingImages(true);
          }}
          onDragOver={(event) => {
            if (getAgentImageFiles(event.dataTransfer).length > 0) event.preventDefault();
          }}
          onDragLeave={(event) => {
            if (
              hasLeftAgentImageDropZone(event.relatedTarget, (target) =>
                event.currentTarget.contains(target),
              )
            ) {
              setIsDraggingImages(false);
            }
          }}
          onDrop={handleDrop}
        >
          {header ? <div className="ai-sidebar-input-header">{header}</div> : null}
          <div
            className="agent-image-drop-overlay"
            aria-hidden="true"
          >
            <span className="agent-image-drop-overlay-content">
              <CloudUpload size={16} />
              {t("writing.aiSidebar.dropImageAttachments")}
            </span>
          </div>
          <AnimatePresence
            initial={false}
            mode="wait"
          >
            {bodyMode === "special_panels" ? (
              <motion.div
                key="special-panels"
                className="ai-sidebar-input-body"
                data-mode="special_panels"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.18, ease: "easeOut" }}
              >
                {specialPanels}
              </motion.div>
            ) : readOnly ? (
              <motion.div
                key="read-only"
                className="ai-sidebar-input-body"
                data-mode="read_only"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.18, ease: "easeOut" }}
              >
                <Box className="agent-input__notice">{readOnlyMessage}</Box>
              </motion.div>
            ) : (
              <motion.div
                key="composer"
                className="ai-sidebar-input-body"
                data-mode="composer"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.18, ease: "easeOut" }}
              >
                {automaticMention && automaticMention.markup === "mention" ? (
                  <div className="agent-input-current-entry">
                    <Text
                      size="1"
                      color="gray"
                      className="agent-input-current-entry-label"
                    >
                      {t("writing.aiSidebar.currentEntryReference")}
                    </Text>
                    <div className="agent-input-current-entry-chip">
                      <MentionChip
                        kind={automaticMention.kind}
                        label={getMentionDisplayLabel(automaticMention)}
                      />
                      <button
                        type="button"
                        className="agent-input-current-entry-remove"
                        disabled={isComposerLocked}
                        aria-label={t("writing.aiSidebar.removeCurrentEntryReference", {
                          label: getMentionDisplayLabel(automaticMention),
                        })}
                        onClick={onRemoveAutomaticComposerMarkup}
                      >
                        <X
                          size={12}
                          aria-hidden="true"
                        />
                      </button>
                    </div>
                  </div>
                ) : null}
                {attachments.length > 0 ? (
                  <PhotoProvider>
                    <div className="agent-image-attachment-strip">
                      {attachments.map((attachment) => {
                        const fileName =
                          attachment.file?.name ??
                          attachment.uploadedAttachment?.fileName ??
                          t("writing.aiSidebar.imageFallbackAlt");
                        return (
                          <div
                            key={attachment.id}
                            className="agent-image-attachment-preview"
                          >
                            <PhotoView src={attachment.previewUrl}>
                              <button
                                type="button"
                                className="agent-image-preview-trigger"
                                aria-label={t("writing.aiSidebar.viewImage", { fileName })}
                              >
                                <img
                                  src={attachment.previewUrl}
                                  alt={fileName}
                                />
                              </button>
                            </PhotoView>
                            <button
                              type="button"
                              className="agent-image-attachment-remove"
                              aria-label={t("writing.aiSidebar.removeImage", { fileName })}
                              onClick={() => handleRemoveAttachment(attachment.id)}
                            >
                              <X size={12} />
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  </PhotoProvider>
                ) : null}
                <AgentComposerEditor
                  projectId={projectId}
                  contextMode={contextMode}
                  placeholder={getPlaceholder()}
                  value={value}
                  disabled={isComposerLocked}
                  onOpenMentionChapter={onOpenMentionChapter}
                  onMentionSuggestionsChange={setMentionSuggestions}
                  onPasteFiles={handlePastedFiles}
                  onDropFiles={handleDroppedFiles}
                  onChange={handleComposerChange}
                  onHistoryNavigate={handleHistoryNavigate}
                  historyNavigationActive={historyState.index !== null}
                  onSubmit={handleSubmit}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {readOnly ? null : (
        <Flex
          justify="between"
          align="center"
          gap="2"
        >
          <Flex
            align="center"
            gap="2"
            wrap="wrap"
            className="agent-input__controls"
          >
            {isModelsLoading ? (
              <Flex
                align="center"
                gap="2"
                className="agent-input__actions"
              >
                <Spinner size={18} />
                <Text
                  size="1"
                  color="gray"
                >
                  {t("common.loading")}
                </Text>
              </Flex>
            ) : models.length === 0 || modelsError ? (
              <Tooltip content={t("writing.aiSidebar.noModelsTooltip")}>
                <Flex
                  align="center"
                  gap="1"
                  className="ai-sidebar-no-models"
                >
                  <Text
                    size="1"
                    color="gray"
                  >
                    {t("writing.aiSidebar.noModelsMessage")}
                  </Text>
                  <button
                    type="button"
                    className="ai-sidebar-no-models-action"
                    onClick={onGoToSettings}
                  >
                    <Text
                      size="1"
                      className="ai-sidebar-no-models-action-text"
                    >
                      {t("writing.aiSidebar.noModelsAction")}
                    </Text>
                    <ExternalLink
                      size={12}
                      aria-hidden="true"
                    />
                  </button>
                </Flex>
              </Tooltip>
            ) : (
              <>
                {agentOptions.length > 0 && onAgentChange ? (
                  <Box className="ai-sidebar-model-selector agent-input__agent-selector">
                    <SimpleSelect
                      value={agentKey ?? ""}
                      options={agentOptions}
                      onChange={onAgentChange}
                      disabled={disabled || readOnly || agentChangeDisabled}
                      size="1"
                      hideTriggerChevron
                      contentClassName="ai-sidebar-agent-select-content"
                      triggerClassName="ai-sidebar-inline-select-trigger ai-sidebar-agent-select-trigger"
                      triggerStyle={{
                        fontSize: "var(--font-size-sm)",
                        border: "none",
                        background: "transparent",
                        boxShadow: "none",
                      }}
                    />
                  </Box>
                ) : null}
                <Flex
                  align="center"
                  gap="2"
                  className="ai-sidebar-model-reasoning-group"
                >
                  <Box className="ai-sidebar-model-selector agent-input__model-selector">
                    <ModelIdSelect
                      value={modelId}
                      models={models}
                      onChange={onModelChange}
                      editable={false}
                      allowCustomValue={false}
                      compact
                      triggerPrefix={modelTriggerPrefix}
                      hideTriggerChevron
                      triggerClassName="ai-sidebar-inline-select-trigger"
                      triggerStyle={{
                        fontSize: "var(--font-size-sm)",
                        border: "none",
                        background: "transparent",
                        boxShadow: "none",
                      }}
                    />
                  </Box>
                  {selectedModel &&
                  onModelSpeedChange &&
                  (selectedModel.speedVariants?.fast || modelSpeed === "fast") ? (
                    <Box className="ai-sidebar-speed-selector">
                      <SimpleSelect
                        value={modelSpeed}
                        options={[
                          { value: "standard", label: "Standard" },
                          ...(selectedModel.speedVariants?.fast
                            ? [{ value: "fast", label: "Fast" }]
                            : []),
                        ]}
                        placeholder={t("assistant.modelSpeed")}
                        onChange={(value) => onModelSpeedChange(value as "standard" | "fast")}
                        disabled={disabled}
                        size="1"
                        triggerClassName="ai-sidebar-inline-select-trigger ai-sidebar-speed-trigger"
                      />
                    </Box>
                  ) : null}
                  {selectedModel && onReasoningEffortChange ? (
                    <Tooltip
                      content={
                        reasoningEffortStatus === "unsupported"
                          ? t("assistant.reasoningEffortUnsupported")
                          : t("assistant.reasoningEffortUnknown")
                      }
                      open={reasoningEffortStatus === "supported" ? false : undefined}
                    >
                      <Box className="ai-sidebar-reasoning-effort-selector">
                        <SimpleSelect
                          value={effectiveReasoningEffort}
                          options={reasoningEffortOptions}
                          onChange={onReasoningEffortChange}
                          disabled={
                            disabled ||
                            (reasoningEffortStatus !== "supported" &&
                              effectiveReasoningEffort === "off")
                          }
                          size="1"
                          hideTriggerChevron
                          triggerClassName="ai-sidebar-inline-select-trigger ai-sidebar-reasoning-effort-trigger"
                          triggerStyle={{
                            fontSize: "var(--font-size-sm)",
                            border: "none",
                            background: "transparent",
                            boxShadow: "none",
                          }}
                        />
                      </Box>
                    </Tooltip>
                  ) : null}
                </Flex>
              </>
            )}
          </Flex>

          <Flex
            align="center"
            gap="2"
          >
            {isSending && onDeliveryModeChange ? (
              <DeliveryModeSelect
                value={deliveryMode}
                onChange={onDeliveryModeChange}
              />
            ) : null}
            <AgentIndexStatusIndicator projectId={projectId} />

            <Tooltip
              content={
                toolApprovalBypassEnabled
                  ? t("writing.aiSidebar.toolApprovalBypassOn")
                  : t("writing.aiSidebar.toolApprovalBypassOff")
              }
            >
              <IconButton
                type="button"
                variant="ghost"
                size="1"
                onClick={onToggleToolApprovalBypass}
                disabled={toolApprovalBypassDisabled}
                aria-pressed={toolApprovalBypassEnabled}
                aria-label={
                  toolApprovalBypassEnabled
                    ? t("writing.aiSidebar.toolApprovalBypassOn")
                    : t("writing.aiSidebar.toolApprovalBypassOff")
                }
                className="agent-input__action"
                style={{
                  background: toolApprovalBypassEnabled ? "var(--green-a3)" : "transparent",
                  color: toolApprovalBypassEnabled ? "var(--green-11)" : "#111111",
                }}
              >
                <ShieldCheck size={14} />
              </IconButton>
            </Tooltip>

            <motion.div
              animate={{
                opacity: buttonActive ? 1 : 0.2,
                scale: 1,
              }}
              transition={{ duration: 0.15, ease: "easeOut" }}
              className="agent-input__send-animation"
            >
              <IconButton
                variant="solid"
                size="1"
                className="ai-sidebar-send-button agent-input__send"
                onClick={shouldAbort ? onAbort : handleSubmit}
                disabled={shouldAbort ? false : !canSend}
                aria-disabled={!buttonActive || undefined}
                style={{ pointerEvents: buttonActive ? undefined : "none" }}
              >
                {shouldAbort ? (
                  <Square
                    size={12}
                    fill="currentColor"
                  />
                ) : disabled ? (
                  <Spinner size={18} />
                ) : (
                  <ArrowUp size={14} />
                )}
              </IconButton>
            </motion.div>
          </Flex>
        </Flex>
      )}
    </Box>
  );
}
