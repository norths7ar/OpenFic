import "./agent-definitions-settings.css";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Box,
  Button,
  Checkbox,
  Flex,
  Switch,
  ScrollArea,
  Text,
  TextArea,
  TextField,
  Dialog,
  IconButton,
  Badge,
  Tooltip,
} from "@radix-ui/themes";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  Copy,
  ExternalLink,
  Info,
  MoreHorizontal,
  Plus,
  RefreshCw,
  RotateCcw,
  Trash2,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useState, useCallback, useEffect, useMemo } from "react";
import { useForm, useController } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { z } from "zod";

import { LabeledSelect, ModelIdSelect, type ModelIdSelectOption } from "@/components";
import { ContextMenu, type ContextMenuItem, toast, ConfirmDialog, Spinner } from "@/components";
import { AgentBrandIcon } from "@/components/agent-brand-icon";
import {
  DEFAULT_AGENT_COLOR,
  DEFAULT_AGENT_ICON,
  getAgentDisplayDescription,
} from "@/lib/agent-branding";
import type { Skill } from "@/lib/skill.types";
import { useLlmModelOptions } from "@/lib/use-llm-model-options";

import {
  AGENT_DEFINITION_MENU_ACTIONS,
  getAgentDefinitionMenuActions,
} from "../lib/agent-definition-menu";
import {
  fetchAgentToolCategories,
  fetchAgentDefinitions,
  createAgentDefinition,
  updateAgentDefinition,
  resetAgentDefinition,
  deleteAgentDefinition,
} from "../lib/agent-definitions-api";
import type {
  AgentToolCategoryResponse,
  AgentDefinitionResponse,
  AgentDefinitionCreateRequest,
} from "../lib/agent-definitions.types";
import {
  getAgentKindLabel,
  getAgentKindOptions,
  SYSTEM_DEFAULT_MODEL_REFERENCE,
  SYSTEM_LIGHT_MODEL_REFERENCE,
} from "../lib/agent-definitions.types";
import { fetchSettings } from "../lib/settings-api";
import { fetchSkills } from "../lib/skills-api";
import { AgentBrandingPicker } from "./agent-branding-picker";
import { AgentSettingsLockNotice } from "./agent-settings-lock-notice";

const AgentEditSchema = z.object({
  displayName: z.string(),
  description: z.string(),
  kind: z.enum(["primary", "subagent"]),
  color: z.string().nullable(),
  icon: z.string().nullable(),
  modelId: z.string(),
  enabledToolCategories: z.array(z.string()),
  enabledSkills: z.array(z.string()),
  delegatableAgents: z.array(z.string()),
});
type AgentEditValues = z.infer<typeof AgentEditSchema>;
const AgentCreateSchema = z.object({
  kind: z.enum(["primary", "subagent"]),
  key: z
    .string()
    .trim()
    .min(1)
    .max(50)
    .regex(/^[a-z0-9-]+$/),
  displayName: z.string(),
  description: z.string(),
  color: z.string().nullable(),
  icon: z.string().nullable(),
});
type AgentCreateValues = z.infer<typeof AgentCreateSchema>;

const LIST_WIDTH = 280;
const SUBAGENT_RESTRICTED_TOOL_CATEGORIES = new Set(["orchestration", "interaction"]);
const MotionBox = motion.create(Box);

const mobilePageVariants = {
  enter: (direction: number) => ({
    x: direction > 0 ? "100%" : "-100%",
  }),
  center: {
    x: 0,
  },
  exit: (direction: number) => ({
    x: direction > 0 ? "-100%" : "100%",
  }),
};

interface AgentListMenuState {
  key: string;
  position: { x: number; y: number };
}

function getEffectiveModelSelection(modelId: string | null): string {
  if (!modelId) return SYSTEM_DEFAULT_MODEL_REFERENCE;
  return modelId;
}

function getEnabledToolCategoriesForAgent(
  kind: "primary" | "subagent",
  categories: string[],
): string[] {
  if (kind !== "subagent") return categories;
  return categories.filter((category) => !SUBAGENT_RESTRICTED_TOOL_CATEGORIES.has(category));
}

function buildAgentModelOptions(
  llmModelOptions: ModelIdSelectOption[],
  t: (key: string) => string,
): ModelIdSelectOption[] {
  return [
    {
      value: SYSTEM_DEFAULT_MODEL_REFERENCE,
      id: t("settings.agentsFollowSystemSetting"),
      name: t("settings.agentsSystemDefaultModel"),
      taskType: "llm",
    },
    {
      value: SYSTEM_LIGHT_MODEL_REFERENCE,
      id: t("settings.agentsFollowSystemSetting"),
      name: t("settings.agentsSystemLightModel"),
      taskType: "llm",
    },
    ...llmModelOptions,
  ];
}

interface AgentFormProps {
  def: AgentDefinitionResponse;
  definitions: AgentDefinitionResponse[];
  llmModelOptions: ModelIdSelectOption[];
  hasLlmModels: boolean;
  toolCategoryOptions: AgentToolCategoryResponse[];
  skills: Skill[];
  onCloseSettings?: () => void;
  onKindPreviewChange: (key: string, kind: AgentDefinitionResponse["kind"] | null) => void;
  onUpdated: (definition?: AgentDefinitionResponse) => void;
  isAgentSettingsLocked: boolean;
}

function AgentForm({
  def,
  definitions,
  llmModelOptions,
  hasLlmModels,
  toolCategoryOptions,
  skills,
  onCloseSettings,
  onKindPreviewChange,
  onUpdated,
  isAgentSettingsLocked,
}: AgentFormProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const {
    control: formControl,
    getValues: formGetValues,
    handleSubmit: formSubmit,
  } = useForm<AgentEditValues>({
    resolver: zodResolver(AgentEditSchema),
    defaultValues: {
      displayName: def.display_name,
      description: def.description,
      kind: def.kind,
      color: def.color ?? DEFAULT_AGENT_COLOR,
      icon: def.icon ?? DEFAULT_AGENT_ICON,
      modelId: getEffectiveModelSelection(def.model_id),
      enabledToolCategories: getEnabledToolCategoriesForAgent(
        def.kind,
        def.enabled_tool_categories,
      ),
      enabledSkills: [...def.enabled_skills],
      delegatableAgents: [...def.delegatable_agents],
    },
  });
  const {
    field: { value: formDisplayName, onChange: setFormDisplayName },
  } = useController({ control: formControl, name: "displayName" });
  const {
    field: { value: formDescription, onChange: setFormDescription },
  } = useController({ control: formControl, name: "description" });
  const {
    field: { value: formKind, onChange: setFormKind },
  } = useController({ control: formControl, name: "kind" });
  const {
    field: { value: formColor, onChange: setFormColor },
  } = useController({ control: formControl, name: "color" });
  const {
    field: { value: formIcon, onChange: setFormIcon },
  } = useController({ control: formControl, name: "icon" });
  const {
    field: { value: formModelId, onChange: setFormModelId },
  } = useController({ control: formControl, name: "modelId" });
  const {
    field: { value: formEnabledToolCategories, onChange: setFormEnabledToolCategories },
  } = useController({ control: formControl, name: "enabledToolCategories" });
  const {
    field: { value: formEnabledSkills, onChange: setFormEnabledSkills },
  } = useController({ control: formControl, name: "enabledSkills" });
  const {
    field: { value: formDelegatableAgents, onChange: setFormDelegatableAgents },
  } = useController({ control: formControl, name: "delegatableAgents" });
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);

  useEffect(() => () => onKindPreviewChange(def.key, null), [def.key, onKindPreviewChange]);

  const allSubagents = useMemo(
    () => definitions.filter((d) => d.kind === "subagent" && d.enabled),
    [definitions],
  );

  const delegatableOptions = useMemo(
    () =>
      allSubagents
        .filter((d) => d.key !== def.key)
        .map((d) => ({
          value: d.key,
          label: d.display_name || d.key,
        })),
    [allSubagents, def.key],
  );

  const hasFormChanges = useMemo(() => {
    return (
      formDisplayName !== def.display_name ||
      formDescription !== def.description ||
      formKind !== def.kind ||
      formColor !== (def.color ?? DEFAULT_AGENT_COLOR) ||
      formIcon !== (def.icon ?? DEFAULT_AGENT_ICON) ||
      formModelId !== getEffectiveModelSelection(def.model_id) ||
      JSON.stringify(formEnabledToolCategories) !==
        JSON.stringify(getEnabledToolCategoriesForAgent(def.kind, def.enabled_tool_categories)) ||
      JSON.stringify(formEnabledSkills) !== JSON.stringify(def.enabled_skills) ||
      JSON.stringify(formDelegatableAgents) !== JSON.stringify(def.delegatable_agents)
    );
  }, [
    def,
    formDescription,
    formDisplayName,
    formKind,
    formColor,
    formIcon,
    formModelId,
    formEnabledToolCategories,
    formEnabledSkills,
    formDelegatableAgents,
  ]);

  const isPrimary = formKind === "primary";
  const hasDelegationCapability = formEnabledToolCategories.includes("orchestration");
  const canChangeKind = def.source === "custom";
  const selectableToolCategoryOptions = useMemo(
    () =>
      toolCategoryOptions.filter(
        (option) => formKind !== "subagent" || !SUBAGENT_RESTRICTED_TOOL_CATEGORIES.has(option.key),
      ),
    [formKind, toolCategoryOptions],
  );

  const updateMutation = useMutation({
    mutationFn: async () => {
      return updateAgentDefinition(def.key, {
        display_name: formDisplayName,
        description: formDescription,
        ...(canChangeKind ? { kind: formKind } : {}),
        model_id: formModelId,
        color: formColor,
        icon: formIcon,
        enabled_tool_categories: getEnabledToolCategoriesForAgent(
          formKind,
          formEnabledToolCategories,
        ),
        enabled_skills: formEnabledSkills,
        delegatable_agents: isPrimary ? formDelegatableAgents : [],
      });
    },
    onSuccess: (definition) => {
      onUpdated(definition);
      toast.success(t("common.saveSuccess"));
    },
    onError: () => toast.error(t("settings.agentsSaveFailed")),
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteAgentDefinition(def.key),
    onSuccess: () => {
      onUpdated();
      setConfirmDeleteOpen(false);
      toast.success(t("settings.agentsDeleteSuccess"));
    },
    onError: () => toast.error(t("settings.agentsDeleteFailed")),
  });

  const handleGoToPromptChain = useCallback(() => {
    onCloseSettings?.();
    const params = new URLSearchParams({
      prompt: `${def.source === "builtin" ? "builtin-agent" : "custom-agent"}--${def.key}`,
    });
    navigate(`/prompt-chains?${params.toString()}`);
  }, [def.key, def.source, navigate, onCloseSettings]);

  const handleToggleDelegatable = useCallback(
    (key: string) => {
      const previous = formGetValues("delegatableAgents");
      setFormDelegatableAgents(
        previous.includes(key) ? previous.filter((item) => item !== key) : [...previous, key],
      );
    },
    [setFormDelegatableAgents, formGetValues],
  );

  const handleKindChange = useCallback(
    (kind: string) => {
      const nextKind = kind as "primary" | "subagent";
      setFormKind(nextKind);
      onKindPreviewChange(def.key, nextKind);
      if (nextKind === "subagent") {
        setFormEnabledToolCategories(
          getEnabledToolCategoriesForAgent(nextKind, formGetValues("enabledToolCategories")),
        );
        setFormDelegatableAgents([]);
      }
    },
    [
      def.key,
      onKindPreviewChange,
      setFormKind,
      setFormEnabledToolCategories,
      setFormDelegatableAgents,
      formGetValues,
    ],
  );

  const handleToggleToolCategory = useCallback(
    (key: string) => {
      const previous = formGetValues("enabledToolCategories");
      setFormEnabledToolCategories(
        previous.includes(key) ? previous.filter((item) => item !== key) : [...previous, key],
      );
    },
    [setFormEnabledToolCategories, formGetValues],
  );

  const handleToggleEnabledSkill = useCallback(
    (skillId: string) => {
      const previous = formGetValues("enabledSkills");
      setFormEnabledSkills(
        previous.includes(skillId)
          ? previous.filter((item) => item !== skillId)
          : [...previous, skillId],
      );
    },
    [setFormEnabledSkills, formGetValues],
  );

  const selectableSkills = useMemo(
    () => skills.filter((skill) => skill.name.trim() && skill.isEnabled),
    [skills],
  );

  return (
    <Flex
      direction="column"
      gap="5"
      key={def.key}
      className="agent-definition-form"
    >
      <Flex
        direction="column"
        gap="1"
      >
        <Text
          size="1"
          weight="medium"
          className="agent-definition-field-label"
        >
          {t("settings.agentsDisplayName")}
        </Text>
        <TextField.Root
          value={formDisplayName}
          onChange={(e) => setFormDisplayName(e.target.value)}
          placeholder={t("settings.agentsDisplayNamePlaceholder")}
          disabled={isAgentSettingsLocked}
        />
      </Flex>

      {canChangeKind ? (
        <Flex
          direction="column"
          gap="1"
        >
          <Flex
            align="center"
            gap="1"
          >
            <Text
              size="1"
              weight="medium"
            >
              {t("settings.agentsKind")}
            </Text>
            <Tooltip
              content={
                <Flex
                  direction="column"
                  gap="1"
                >
                  <Text size="1">{t("settings.agentsKindPrimaryDescription")}</Text>
                  <Text size="1">{t("settings.agentsKindSubagentDescription")}</Text>
                </Flex>
              }
            >
              <button
                type="button"
                className="agent-definition-kind-info-button"
                aria-label={t("settings.agentsKindTooltipLabel")}
              >
                <Info size={14} />
              </button>
            </Tooltip>
          </Flex>
          <LabeledSelect
            value={formKind}
            options={getAgentKindOptions()}
            onChange={handleKindChange}
            disabled={isAgentSettingsLocked}
            triggerStyle={{ width: "100%" }}
          />
        </Flex>
      ) : null}

      <Flex
        direction="column"
        gap="1"
      >
        <Text
          size="1"
          weight="medium"
          className="agent-definition-field-label"
        >
          {t("settings.agentsFieldDescription")}
        </Text>
        <TextArea
          value={formDescription}
          onChange={(event) => setFormDescription(event.target.value)}
          rows={3}
          placeholder={t("settings.agentsDescriptionPlaceholder")}
          disabled={isAgentSettingsLocked}
        />
      </Flex>

      {isPrimary ? (
        <AgentBrandingPicker
          color={formColor}
          icon={formIcon}
          onChange={(color, icon) => {
            setFormColor(color);
            setFormIcon(icon);
          }}
          disabled={isAgentSettingsLocked}
          labelClassName="agent-definition-field-label"
        />
      ) : null}

      <Flex
        direction="column"
        gap="1"
      >
        <Text
          size="1"
          weight="medium"
          className="agent-definition-field-label"
        >
          {t("settings.agentsModelId")}
        </Text>
        <ModelIdSelect
          value={formModelId}
          models={llmModelOptions}
          onChange={setFormModelId}
          editable={false}
          allowCustomValue={false}
          disabled={isAgentSettingsLocked || !hasLlmModels}
          triggerStyle={{ width: "100%" }}
        />
      </Flex>

      <Flex
        direction="column"
        gap="1"
      >
        <Text
          size="1"
          weight="medium"
          className="agent-definition-field-label"
        >
          {t("settings.agentsToolCategories")}
        </Text>
        {selectableToolCategoryOptions.length === 0 ? (
          <Text
            size="2"
            color="gray"
          >
            {t("settings.agentsNoTools")}
          </Text>
        ) : (
          <Flex
            wrap="wrap"
            gap="2"
          >
            {selectableToolCategoryOptions.map((opt) => (
              <label
                key={opt.key}
                className="agent-definitions-settings__option-chip"
                style={{ cursor: isAgentSettingsLocked ? "not-allowed" : "pointer" }}
              >
                <Checkbox
                  checked={formEnabledToolCategories.includes(opt.key)}
                  disabled={isAgentSettingsLocked}
                  onCheckedChange={() => handleToggleToolCategory(opt.key)}
                  className="agent-definitions-settings__option-checkbox"
                />
                {opt.name}
              </label>
            ))}
          </Flex>
        )}
      </Flex>

      <Flex
        direction="column"
        gap="1"
      >
        <Text
          size="1"
          weight="medium"
          className="agent-definition-field-label"
        >
          {t("settings.agentsEnabledSkills")}
        </Text>
        {selectableSkills.length === 0 ? (
          <Text
            size="2"
            color="gray"
          >
            {t("settings.agentsNoSkills")}
          </Text>
        ) : (
          <Flex
            wrap="wrap"
            gap="2"
          >
            {selectableSkills.map((skill) => {
              const disabled = isAgentSettingsLocked || !skill.isComplete;
              return (
                <label
                  key={skill.id}
                  className="agent-definitions-settings__option-chip"
                  style={{
                    cursor: disabled ? "not-allowed" : "pointer",
                    opacity: disabled ? 0.6 : 1,
                  }}
                  title={disabled ? t("settings.agentsSkillUnavailable") : skill.name}
                >
                  <Checkbox
                    checked={formEnabledSkills.includes(skill.id)}
                    disabled={disabled}
                    onCheckedChange={() => handleToggleEnabledSkill(skill.id)}
                    className="agent-definitions-settings__option-checkbox"
                  />
                  {skill.name || t("settingsExtra.skills.untitled")}
                </label>
              );
            })}
          </Flex>
        )}
      </Flex>

      {isPrimary && hasDelegationCapability && (
        <Flex
          direction="column"
          gap="2"
        >
          <Text
            size="1"
            weight="medium"
            className="agent-definition-field-label"
          >
            {t("settings.agentsDelegatableAgents")}
          </Text>
          {delegatableOptions.length === 0 ? (
            <Text
              size="2"
              color="gray"
            >
              {t("settings.agentsNoDelegatableAgents")}
            </Text>
          ) : (
            <Flex
              wrap="wrap"
              gap="2"
            >
              {delegatableOptions.map((opt) => (
                <label
                  key={opt.value}
                  className="agent-definitions-settings__option-chip"
                  style={{ cursor: isAgentSettingsLocked ? "not-allowed" : "pointer" }}
                >
                  <Checkbox
                    checked={formDelegatableAgents.includes(opt.value)}
                    disabled={isAgentSettingsLocked}
                    onCheckedChange={() => handleToggleDelegatable(opt.value)}
                    className="agent-definitions-settings__option-checkbox"
                  />
                  {opt.label}
                </label>
              ))}
            </Flex>
          )}
        </Flex>
      )}

      <Flex
        direction="column"
        gap="1"
      >
        <Text
          size="1"
          weight="medium"
          className="agent-definition-field-label"
        >
          {t("settings.agentsPromptChain")}
        </Text>
        <Flex
          align="center"
          gap="1"
          wrap="wrap"
        >
          <Text
            size="2"
            color="gray"
          >
            {t("settings.agentsPromptChainLocationPrefix", { agent: def.display_name })}
          </Text>
          <button
            type="button"
            onClick={handleGoToPromptChain}
            className="agent-definitions-settings__prompt-link"
          >
            <Text
              size="2"
              className="agent-definitions-settings__link-label"
            >
              {t("settings.agentsPromptChainAction")}
            </Text>
            <ExternalLink size={14} />
          </button>
        </Flex>
      </Flex>

      <Flex
        direction="column"
        gap="2"
        className="agent-definitions-settings__model-hint"
      >
        <Button
          size="2"
          disabled={isAgentSettingsLocked || !hasFormChanges || updateMutation.isPending}
          onClick={formSubmit(() => updateMutation.mutate())}
          className="agent-definitions-settings__save-action"
        >
          {updateMutation.isPending ? t("common.loading") : t("common.save")}
        </Button>
      </Flex>

      <ConfirmDialog
        open={confirmDeleteOpen}
        onOpenChange={(open) => !open && setConfirmDeleteOpen(false)}
        title={t("settings.agentsDelete")}
        description={`${t("settings.agentsDeleteConfirmPrefix")}「${def.display_name}」${t("settings.agentsDeleteConfirmSuffix")}`}
        onConfirm={() => deleteMutation.mutate()}
        confirmText={t("common.delete")}
        cancelText={t("common.cancel")}
        loading={deleteMutation.isPending}
      />
    </Flex>
  );
}

interface AgentDefinitionsSettingsProps {
  onCloseSettings?: () => void;
  mobilePage?: "list" | "detail";
  mobileDirection?: 1 | -1;
  onMobileDetailTitleChange?: (title: string | null) => void;
  onMobilePageChange?: (page: "list" | "detail") => void;
  isAgentSettingsLocked: boolean;
  isAgentSettingsLockLoading: boolean;
}

interface AgentKindPreview {
  key: string;
  kind: AgentDefinitionResponse["kind"];
}

export function AgentDefinitionsSettings({
  onCloseSettings,
  mobilePage,
  mobileDirection: controlledMobileDirection,
  onMobileDetailTitleChange,
  onMobilePageChange,
  isAgentSettingsLocked,
  isAgentSettingsLockLoading,
}: AgentDefinitionsSettingsProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const [formResetVersion, setFormResetVersion] = useState(0);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [createMode, setCreateMode] = useState<"create" | "copy">("create");
  const [copySource, setCopySource] = useState<AgentDefinitionResponse | null>(null);
  const {
    control: newControl,
    handleSubmit: newSubmit,
    formState: { errors: createErrors },
  } = useForm<AgentCreateValues>({
    resolver: zodResolver(AgentCreateSchema),
    defaultValues: {
      kind: "primary",
      key: "",
      displayName: "",
      description: "",
      color: DEFAULT_AGENT_COLOR,
      icon: DEFAULT_AGENT_ICON,
    },
  });
  const {
    field: { value: newKind, onChange: setNewKind },
  } = useController({ control: newControl, name: "kind" });
  const {
    field: { value: newKey, onChange: setNewKey },
  } = useController({ control: newControl, name: "key" });
  const {
    field: { value: newDisplayName, onChange: setNewDisplayName },
  } = useController({ control: newControl, name: "displayName" });
  const {
    field: { value: newDescription, onChange: setNewDescription },
  } = useController({ control: newControl, name: "description" });
  const {
    field: { value: newColor, onChange: setNewColor },
  } = useController({ control: newControl, name: "color" });
  const {
    field: { value: newIcon, onChange: setNewIcon },
  } = useController({ control: newControl, name: "icon" });
  const [kindPreview, setKindPreview] = useState<AgentKindPreview | null>(null);
  const [menuState, setMenuState] = useState<AgentListMenuState | null>(null);
  const [confirmResetKey, setConfirmResetKey] = useState<string | null>(null);
  const [confirmDeleteKey, setConfirmDeleteKey] = useState<string | null>(null);
  const [isMobile, setIsMobile] = useState(false);
  const [internalMobilePage, setInternalMobilePage] = useState<"list" | "detail">("list");
  const [internalMobileDirection, setInternalMobileDirection] = useState<1 | -1>(1);

  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 768);
    checkMobile();
    window.addEventListener("resize", checkMobile);
    return () => window.removeEventListener("resize", checkMobile);
  }, []);

  const {
    data: definitions = [],
    isLoading,
    isFetching,
    error: definitionsError,
    refetch,
  } = useQuery({
    queryKey: ["agent-definitions"],
    queryFn: fetchAgentDefinitions,
    staleTime: 0,
    refetchOnMount: "always",
  });

  const {
    data: toolCategoryOptions = [],
    isLoading: isToolCategoriesLoading,
    error: toolCategoriesError,
    refetch: refetchToolCategories,
  } = useQuery({
    queryKey: ["agent-tool-categories"],
    queryFn: fetchAgentToolCategories,
    staleTime: 0,
    refetchOnMount: "always",
  });

  const {
    data: skillsData,
    isLoading: isSkillsLoading,
    error: skillsError,
    refetch: refetchSkills,
  } = useQuery({
    queryKey: ["skills"],
    queryFn: () => fetchSkills({ page: 1, pageSize: 100 }),
    staleTime: 0,
    refetchOnMount: "always",
  });
  const skills = useMemo(() => skillsData?.items ?? [], [skillsData?.items]);

  const {
    data: settings,
    isLoading: isSettingsLoading,
    error: settingsError,
    refetch: refetchSettings,
  } = useQuery({
    queryKey: ["settings"],
    queryFn: fetchSettings,
  });

  const { options: llmModelOptions, isLoading: isModelOptionsLoading } = useLlmModelOptions();
  const hasLlmModels = llmModelOptions.length > 0;
  const modelOptions = useMemo(
    () => buildAgentModelOptions(llmModelOptions, t),
    [llmModelOptions, t],
  );

  const effectiveSelectedKey = useMemo(() => {
    if (selectedKey && definitions.some((item) => item.key === selectedKey)) {
      return selectedKey;
    }
    return definitions[0]?.key ?? null;
  }, [definitions, selectedKey]);

  const selectedDef = useMemo(
    () => definitions.find((d) => d.key === effectiveSelectedKey) ?? null,
    [definitions, effectiveSelectedKey],
  );
  const currentMobilePage = mobilePage ?? internalMobilePage;
  const currentMobileDirection = controlledMobileDirection ?? internalMobileDirection;

  const handleMobilePageChange = useCallback(
    (page: "list" | "detail") => {
      if (controlledMobileDirection === undefined) {
        setInternalMobileDirection(page === "detail" ? 1 : -1);
      }
      onMobilePageChange?.(page);
      if (mobilePage === undefined) setInternalMobilePage(page);
    },
    [controlledMobileDirection, mobilePage, onMobilePageChange],
  );

  const contentError = definitionsError || toolCategoriesError || skillsError || settingsError;
  const isContentLoading =
    isLoading ||
    isToolCategoriesLoading ||
    isSkillsLoading ||
    isSettingsLoading ||
    isModelOptionsLoading ||
    isAgentSettingsLockLoading ||
    !settings;

  useEffect(() => {
    onMobileDetailTitleChange?.(selectedDef?.display_name || null);
  }, [onMobileDetailTitleChange, selectedDef]);

  const orderedDefinitions = useMemo(
    () =>
      [...definitions].sort((left, right) => {
        if (left.source === right.source) return 0;
        return left.source === "builtin" ? -1 : 1;
      }),
    [definitions],
  );

  const menuTarget = useMemo(
    () => definitions.find((item) => item.key === menuState?.key) ?? null,
    [definitions, menuState],
  );

  const resetTarget = useMemo(
    () => definitions.find((item) => item.key === confirmResetKey) ?? null,
    [confirmResetKey, definitions],
  );

  const deleteTarget = useMemo(
    () => definitions.find((item) => item.key === confirmDeleteKey) ?? null,
    [confirmDeleteKey, definitions],
  );

  const invalidateDefs = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["agent-definitions"] });
  }, [queryClient]);

  const updateDefinitionInList = useCallback(
    (updatedDefinition?: AgentDefinitionResponse) => {
      if (updatedDefinition) {
        queryClient.setQueryData<AgentDefinitionResponse[]>(["agent-definitions"], (current) =>
          current?.map((definition) =>
            definition.key === updatedDefinition.key ? updatedDefinition : definition,
          ),
        );
        setKindPreview((current) => (current?.key === updatedDefinition.key ? null : current));
        return;
      }
      invalidateDefs();
    },
    [invalidateDefs, queryClient],
  );

  const handleKindPreviewChange = useCallback(
    (key: string, kind: AgentDefinitionResponse["kind"] | null) => {
      setKindPreview(kind ? { key, kind } : null);
    },
    [],
  );

  const closeCreateDialog = useCallback(() => {
    setIsCreating(false);
    setCreateMode("create");
    setCopySource(null);
    setNewKind("primary");
    setNewKey("");
    setNewDisplayName("");
    setNewDescription("");
    setNewColor(DEFAULT_AGENT_COLOR);
    setNewIcon(DEFAULT_AGENT_ICON);
  }, [setNewKind, setNewKey, setNewDisplayName, setNewDescription, setNewColor, setNewIcon]);

  useEffect(() => {
    if (!isAgentSettingsLocked) return;
    closeCreateDialog();
    setMenuState(null);
    setConfirmResetKey(null);
    setConfirmDeleteKey(null);
  }, [closeCreateDialog, isAgentSettingsLocked]);

  const openCreateDialog = useCallback(() => {
    if (isAgentSettingsLocked) return;
    setCreateMode("create");
    setCopySource(null);
    setNewKind("primary");
    setNewKey("");
    setNewDisplayName("");
    setNewDescription("");
    setNewColor(DEFAULT_AGENT_COLOR);
    setNewIcon(DEFAULT_AGENT_ICON);
    setIsCreating(true);
  }, [
    isAgentSettingsLocked,
    setNewKind,
    setNewKey,
    setNewDisplayName,
    setNewDescription,
    setNewColor,
    setNewIcon,
  ]);

  const openCopyDialog = useCallback(
    (def: AgentDefinitionResponse) => {
      if (isAgentSettingsLocked) return;
      setCreateMode("copy");
      setCopySource(def);
      setNewKind(def.kind);
      setNewKey(`${def.key}-copy`.replace(/[^a-z0-9-]/g, "").slice(0, 50));
      setNewDisplayName(`${def.display_name} ${t("settings.agentsCopySuffix")}`);
      setNewDescription(def.description);
      setNewColor(def.color ?? DEFAULT_AGENT_COLOR);
      setNewIcon(def.icon ?? DEFAULT_AGENT_ICON);
      setIsCreating(true);
    },
    [
      isAgentSettingsLocked,
      t,
      setNewKind,
      setNewKey,
      setNewDisplayName,
      setNewDescription,
      setNewColor,
      setNewIcon,
    ],
  );

  const createMutation = useMutation({
    mutationFn: async () => {
      const sourceDefinition = copySource;
      const data: AgentDefinitionCreateRequest = {
        key: newKey.trim(),
        display_name: newDisplayName,
        description: newDescription,
        kind: newKind,
        prompt_agent_name: newKey.trim(),
        model_id: sourceDefinition?.model_id ?? SYSTEM_DEFAULT_MODEL_REFERENCE,
        enabled_tool_categories: getEnabledToolCategoriesForAgent(
          newKind,
          sourceDefinition?.enabled_tool_categories ?? [],
        ),
        enabled_skills: sourceDefinition?.enabled_skills ?? [],
        metadata: sourceDefinition?.metadata ?? {},
        color: newColor,
        icon: newIcon,
        delegatable_agents: sourceDefinition?.delegatable_agents ?? [],
      };
      const created = await createAgentDefinition(data);
      if (sourceDefinition && sourceDefinition.enabled === false) {
        return updateAgentDefinition(created.key, { enabled: false });
      }
      return created;
    },
    onSuccess: (result) => {
      invalidateDefs();
      closeCreateDialog();
      setSelectedKey(result.key);
      if (isMobile) handleMobilePageChange("detail");
      toast.success(
        createMode === "copy" ? t("settings.agentsCopySuccess") : t("settings.agentsCreateSuccess"),
      );
    },
    onError: () =>
      toast.error(
        createMode === "copy" ? t("settings.agentsCopyFailed") : t("settings.agentsCreateFailed"),
      ),
  });

  const resetMutation = useMutation({
    mutationFn: (key: string) => resetAgentDefinition(key),
    onSuccess: (result: AgentDefinitionResponse) => {
      updateDefinitionInList(result);
      setFormResetVersion((version) => version + 1);
      invalidateDefs();
      setConfirmResetKey(null);
      setSelectedKey(result.key);
      toast.success(t("settings.agentsResetSuccess"));
    },
    onError: () => toast.error(t("settings.agentsResetFailed")),
  });

  const deleteMutation = useMutation({
    mutationFn: (key: string) => deleteAgentDefinition(key),
    onSuccess: () => {
      invalidateDefs();
      setConfirmDeleteKey(null);
      toast.success(t("settings.agentsDeleteSuccess"));
    },
    onError: () => toast.error(t("settings.agentsDeleteFailed")),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ key, enabled }: { key: string; enabled: boolean }) =>
      updateAgentDefinition(key, { enabled }),
    onMutate: async ({ key, enabled }) => {
      await queryClient.cancelQueries({ queryKey: ["agent-definitions"] });
      const previous = queryClient.getQueryData<AgentDefinitionResponse[]>(["agent-definitions"]);

      if (previous) {
        queryClient.setQueryData<AgentDefinitionResponse[]>(
          ["agent-definitions"],
          previous.map((item) => (item.key === key ? { ...item, enabled } : item)),
        );
      }

      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(["agent-definitions"], context.previous);
      }
      toast.error(t("common.error"));
    },
    onSuccess: (updatedDef) => {
      queryClient.setQueryData<AgentDefinitionResponse[]>(["agent-definitions"], (current) => {
        if (!current) return current;
        return current.map((item) => (item.key === updatedDef.key ? updatedDef : item));
      });
      toast.success(updatedDef.enabled ? t("worldInfo.enabled") : t("worldInfo.disabled"));
    },
    onSettled: () => {
      invalidateDefs();
    },
  });

  const openMenuAt = useCallback(
    (key: string, position: { x: number; y: number }) => {
      if (isAgentSettingsLocked) return;
      setMenuState({ key, position });
    },
    [isAgentSettingsLocked],
  );

  const closeMenu = useCallback(() => {
    setMenuState(null);
  }, []);

  const menuItems = useMemo<ContextMenuItem[]>(() => {
    if (!menuTarget || isAgentSettingsLocked) return [];

    const actions = getAgentDefinitionMenuActions(menuTarget);
    const items: ContextMenuItem[] = [];

    if (actions.includes(AGENT_DEFINITION_MENU_ACTIONS.copy)) {
      items.push({
        id: "copy",
        label: t("settings.agentsCopy"),
        icon: Copy,
        onClick: () => {
          openCopyDialog(menuTarget);
          closeMenu();
        },
      });
    }

    if (actions.includes(AGENT_DEFINITION_MENU_ACTIONS.delete)) {
      items.push({
        id: "delete",
        label: t("settings.agentsDelete"),
        icon: Trash2,
        danger: true,
        onClick: () => {
          setSelectedKey(menuTarget.key);
          setConfirmDeleteKey(menuTarget.key);
          closeMenu();
        },
      });
    }

    if (actions.includes(AGENT_DEFINITION_MENU_ACTIONS.reset)) {
      items.push({
        id: "reset",
        label: t("settings.agentsReset"),
        icon: RotateCcw,
        onClick: () => {
          setSelectedKey(menuTarget.key);
          setConfirmResetKey(menuTarget.key);
          closeMenu();
        },
      });
    }

    return items;
  }, [
    closeMenu,
    menuTarget,
    openCopyDialog,
    setConfirmDeleteKey,
    setConfirmResetKey,
    setSelectedKey,
    t,
    isAgentSettingsLocked,
  ]);

  const renderAgentListItem = (def: AgentDefinitionResponse) => {
    const displayKind = kindPreview?.key === def.key ? kindPreview.kind : def.kind;

    return (
      <div
        key={def.key}
        role="button"
        tabIndex={0}
        className={`agent-definition-item${effectiveSelectedKey === def.key ? " agent-definition-item--active" : ""}${menuState?.key === def.key ? " agent-definition-item--menu-open" : ""}`}
        onClick={() => {
          setSelectedKey(def.key);
          if (isMobile) handleMobilePageChange("detail");
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setSelectedKey(def.key);
            if (isMobile) handleMobilePageChange("detail");
          }
        }}
        onContextMenu={(event) => {
          event.preventDefault();
          openMenuAt(def.key, { x: event.clientX, y: event.clientY });
        }}
      >
        <Flex
          direction="column"
          gap="1"
          className="agent-definition-item-content"
        >
          <Flex
            align="start"
            justify="between"
            gap="2"
            className="agent-definition-item-row"
          >
            <Flex
              align="center"
              gap="2"
              className="agent-definition-item-title-row"
            >
              <span
                className="agent-definition-kind-icon"
                aria-label={getAgentKindLabel(displayKind)}
                title={getAgentKindLabel(displayKind)}
              >
                {displayKind === "primary" ? (
                  <AgentBrandIcon
                    color={def.color}
                    icon={def.icon}
                    size={14}
                  />
                ) : (
                  <Bot size={14} />
                )}
              </span>
              <Text
                size="2"
                truncate
                weight={effectiveSelectedKey === def.key ? "medium" : "regular"}
              >
                {def.display_name}
              </Text>
              {displayKind === "primary" ? (
                <Badge
                  size="1"
                  variant="soft"
                  color="yellow"
                >
                  {t("settings.agentsPrimaryBadge")}
                </Badge>
              ) : null}
              {def.source === "builtin" ? (
                <Badge
                  size="1"
                  variant="soft"
                  color="green"
                >
                  {t("settings.agentsBuiltin")}
                </Badge>
              ) : null}
            </Flex>

            <Flex
              align="center"
              gap="1"
              className="agent-definition-item-actions"
            >
              <Switch
                size="1"
                checked={def.enabled}
                disabled={isAgentSettingsLocked || toggleMutation.isPending}
                onClick={(event) => event.stopPropagation()}
                onCheckedChange={(checked) => {
                  void toggleMutation.mutateAsync({ key: def.key, enabled: checked === true });
                }}
              />
              <IconButton
                type="button"
                variant="ghost"
                color="gray"
                size="1"
                className="agent-definition-item-menu"
                aria-label={t("settings.agentsMenu")}
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  const rect = event.currentTarget.getBoundingClientRect();
                  openMenuAt(def.key, { x: rect.right, y: rect.bottom + 4 });
                }}
                disabled={isAgentSettingsLocked}
              >
                <MoreHorizontal size={14} />
              </IconButton>
            </Flex>
          </Flex>
          <Text
            size="1"
            color="gray"
            className="agent-definition-item-description"
          >
            {getAgentDisplayDescription(def.key, def.description || "") ||
              t("settings.agentsNoDescription")}
          </Text>
        </Flex>
      </div>
    );
  };

  const listContent = (
    <Box
      className="agent-definitions-list-panel"
      style={isMobile ? undefined : { width: LIST_WIDTH }}
    >
      <Box className="agent-definitions-list-header">
        <Flex
          align="center"
          justify="between"
          gap="2"
          className="agent-definitions-list-header-row"
        >
          <Text
            size="2"
            weight="medium"
            className="agent-definitions-list-count"
          >
            {t("settings.agentsTotalCount", { count: definitions.length })}
          </Text>
          <Flex
            align="center"
            gap="1"
            className="agent-definitions-list-actions"
          >
            <IconButton
              size="2"
              variant="ghost"
              color="gray"
              aria-label={t("settings.agentsNewAgent")}
              onClick={openCreateDialog}
              disabled={isAgentSettingsLocked}
            >
              <Plus size={14} />
            </IconButton>
            <IconButton
              size="2"
              variant="ghost"
              color="gray"
              aria-label={t("common.refresh")}
              onClick={() => void refetch()}
              disabled={isFetching}
            >
              <RefreshCw
                size={14}
                className={isFetching ? "animate-spin" : undefined}
              />
            </IconButton>
          </Flex>
        </Flex>
      </Box>

      <ScrollArea className="agent-definitions-settings__list-scroll">
        {isLoading ? (
          <Flex
            align="center"
            justify="center"
            className="agent-definitions-settings__list-loading"
          >
            <Text
              size="2"
              color="gray"
            >
              {t("common.loading")}
            </Text>
          </Flex>
        ) : (
          <Flex
            direction="column"
            gap="2"
            className="agent-definitions-list-body"
          >
            {orderedDefinitions.map(renderAgentListItem)}

            {definitions.length === 0 ? (
              <Flex
                align="center"
                justify="center"
                className="agent-definitions-settings__empty-list"
              >
                <Text
                  size="2"
                  color="gray"
                >
                  {t("settings.agentsEmpty")}
                </Text>
              </Flex>
            ) : null}
          </Flex>
        )}
      </ScrollArea>
    </Box>
  );

  const detailContent = !selectedDef ? (
    <Flex
      direction="column"
      align="center"
      justify="center"
      gap="2"
      className="agent-definitions-empty-state"
    >
      <Bot
        size={32}
        className="agent-definitions-settings__empty-icon"
      />
      <Text
        size="2"
        color="gray"
      >
        {t("settings.agentsSelectHint")}
      </Text>
    </Flex>
  ) : (
    <AgentForm
      key={`${selectedDef.key}:${formResetVersion}`}
      def={selectedDef}
      definitions={definitions}
      llmModelOptions={modelOptions}
      hasLlmModels={hasLlmModels}
      toolCategoryOptions={toolCategoryOptions}
      skills={skills}
      onCloseSettings={onCloseSettings}
      onKindPreviewChange={handleKindPreviewChange}
      onUpdated={updateDefinitionInList}
      isAgentSettingsLocked={isAgentSettingsLocked}
    />
  );

  return (
    <>
      {contentError ? (
        <Flex
          direction="column"
          align="center"
          justify="center"
          gap="3"
        >
          <Text color="red">{t("common.error")}</Text>
          <Button
            onClick={() => {
              void refetch();
              void refetchToolCategories();
              void refetchSkills();
              void refetchSettings();
            }}
          >
            {t("common.retryRequest")}
          </Button>
        </Flex>
      ) : isContentLoading ? (
        <Flex
          align="center"
          justify="center"
          className="agent-definitions-settings__loading"
        >
          <Spinner size={18} />
        </Flex>
      ) : isMobile ? (
        <Flex
          direction="column"
          className="agent-definitions-settings-content"
        >
          <AgentSettingsLockNotice isLocked={isAgentSettingsLocked} />
          <Flex className="agent-definitions-layout agent-definitions-layout--mobile">
            <Box className="settings-dialog-mobile-page-stack">
              <AnimatePresence
                initial={false}
                custom={currentMobileDirection}
                mode="sync"
              >
                {currentMobilePage === "list" ? (
                  <MotionBox
                    key="agents-mobile-list"
                    custom={currentMobileDirection}
                    variants={mobilePageVariants}
                    initial="enter"
                    animate="center"
                    exit="exit"
                    transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                    className="settings-dialog-mobile-page"
                  >
                    <Box className="settings-dialog-mobile-page-padding">
                      <Box className="settings-dialog-mobile-page-content">{listContent}</Box>
                    </Box>
                  </MotionBox>
                ) : (
                  <MotionBox
                    key="agents-mobile-detail"
                    custom={currentMobileDirection}
                    variants={mobilePageVariants}
                    initial="enter"
                    animate="center"
                    exit="exit"
                    transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                    className="settings-dialog-mobile-page"
                  >
                    <Box className="agent-definitions-detail-panel agent-definitions-detail-panel--mobile">
                      {detailContent}
                    </Box>
                  </MotionBox>
                )}
              </AnimatePresence>
            </Box>
          </Flex>
        </Flex>
      ) : (
        <Flex
          direction="column"
          className="agent-definitions-settings-content"
        >
          <AgentSettingsLockNotice isLocked={isAgentSettingsLocked} />
          <Flex className="agent-definitions-layout">
            {listContent}

            <Box className="agent-definitions-detail-panel">{detailContent}</Box>
          </Flex>
        </Flex>
      )}

      <ContextMenu
        position={menuState?.position ?? null}
        items={menuItems}
        onClose={closeMenu}
      />

      <Dialog.Root
        open={isCreating}
        onOpenChange={(open) => (!open ? closeCreateDialog() : setIsCreating(true))}
      >
        <Dialog.Content className="agent-definitions-settings__create-dialog">
          <Dialog.Title>
            {createMode === "copy" ? t("settings.agentsCopy") : t("settings.agentsNewAgent")}
          </Dialog.Title>
          <Flex
            direction="column"
            gap="3"
            className="agent-definitions-settings__creation-fields"
          >
            <Flex
              direction="column"
              gap="1"
            >
              <Text
                size="1"
                weight="medium"
              >
                {t("settings.agentsKey")}
              </Text>
              <TextField.Root
                aria-invalid={Boolean(createErrors.key)}
                value={newKey}
                onChange={(event) =>
                  setNewKey(event.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))
                }
                placeholder={t("settings.agentsKeyPlaceholder")}
                disabled={isAgentSettingsLocked}
              />
              {createErrors.key && (
                <Text
                  color="red"
                  size="1"
                >
                  {t("settings.agentsKeyInvalid")}
                </Text>
              )}
            </Flex>

            <Flex
              direction="column"
              gap="1"
            >
              <Text
                size="1"
                weight="medium"
              >
                {t("settings.agentsDisplayName")}
              </Text>
              <TextField.Root
                value={newDisplayName}
                onChange={(event) => setNewDisplayName(event.target.value)}
                placeholder={t("settings.agentsDisplayNamePlaceholder")}
                disabled={isAgentSettingsLocked}
              />
            </Flex>

            <Flex
              direction="column"
              gap="1"
            >
              <Text
                size="1"
                weight="medium"
              >
                {t("settings.agentsFieldDescription")}
              </Text>
              <TextArea
                value={newDescription}
                onChange={(event) => setNewDescription(event.target.value)}
                rows={3}
                placeholder={t("settings.agentsDescriptionPlaceholder")}
                disabled={isAgentSettingsLocked}
              />
            </Flex>

            <Flex
              direction="column"
              gap="1"
            >
              <Flex
                align="center"
                gap="1"
              >
                <Text
                  size="1"
                  weight="medium"
                >
                  {t("settings.agentsKind")}
                </Text>
                <Tooltip
                  content={
                    <Flex
                      direction="column"
                      gap="1"
                    >
                      <Text size="1">{t("settings.agentsKindPrimaryDescription")}</Text>
                      <Text size="1">{t("settings.agentsKindSubagentDescription")}</Text>
                    </Flex>
                  }
                >
                  <button
                    type="button"
                    className="agent-definition-kind-info-button"
                    aria-label={t("settings.agentsKindTooltipLabel")}
                  >
                    <Info size={14} />
                  </button>
                </Tooltip>
              </Flex>
              <LabeledSelect
                value={newKind}
                options={getAgentKindOptions()}
                onChange={(value) => setNewKind(value as "primary" | "subagent")}
                disabled={isAgentSettingsLocked}
                triggerStyle={{ width: "100%" }}
              />
            </Flex>

            {newKind === "primary" ? (
              <AgentBrandingPicker
                color={newColor}
                icon={newIcon}
                onChange={(color, icon) => {
                  setNewColor(color);
                  setNewIcon(icon);
                }}
                disabled={isAgentSettingsLocked}
              />
            ) : null}
          </Flex>

          <Flex
            gap="2"
            justify="end"
            className="agent-definitions-settings__creation-actions"
          >
            <Button
              variant="soft"
              color="gray"
              onClick={closeCreateDialog}
            >
              {t("common.cancel")}
            </Button>
            <Button
              disabled={
                isAgentSettingsLocked ||
                !newKey.trim() ||
                !newDisplayName.trim() ||
                createMutation.isPending
              }
              onClick={newSubmit(() => createMutation.mutate())}
            >
              {createMutation.isPending
                ? t("common.loading")
                : t(createMode === "copy" ? "settings.agentsCopy" : "common.create")}
            </Button>
          </Flex>
        </Dialog.Content>
      </Dialog.Root>

      <ConfirmDialog
        open={Boolean(resetTarget)}
        onOpenChange={(open) => !open && setConfirmResetKey(null)}
        title={t("settings.agentsReset")}
        description={t("settings.agentsResetConfirm")}
        onConfirm={() => resetTarget && resetMutation.mutate(resetTarget.key)}
        confirmText={t("settings.agentsReset")}
        cancelText={t("common.cancel")}
        loading={resetMutation.isPending}
      />

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => !open && setConfirmDeleteKey(null)}
        title={t("settings.agentsDelete")}
        description={
          deleteTarget
            ? `${t("settings.agentsDeleteConfirmPrefix")}「${deleteTarget.display_name}」${t("settings.agentsDeleteConfirmSuffix")}`
            : ""
        }
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget.key)}
        confirmText={t("common.delete")}
        cancelText={t("common.cancel")}
        loading={deleteMutation.isPending}
      />
    </>
  );
}
