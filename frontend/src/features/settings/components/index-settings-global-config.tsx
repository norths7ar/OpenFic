import "./index-settings-global-config.css";
import { Box, Flex, Text } from "@radix-ui/themes";
import { useTranslation } from "react-i18next";

import { MultiSelectField, UnitTextField } from "@/components";
import { ModelIdSelect, type ModelIdSelectOption } from "@/components/model-id-select";
import { LabeledSelect } from "@/components/select";
import type { IndexAutoStrategy, IndexMode } from "@/lib/index-status";

import type { Settings } from "../lib/settings.types";
import { IndexSettingsSectionHeader } from "./index-settings-section-header";

interface IndexSettingsGlobalConfigProps {
  settings: Settings;
  embeddingModelOptions: ModelIdSelectOption[];
  rerankModelOptions: ModelIdSelectOption[];
  projectOptions: Array<{ value: string; label: string }>;
  modeOptions: Array<{ value: string; label: string }>;
  autoStrategyOptions: Array<{ value: string; label: string }>;
  chunkSize: string;
  chunkOverlap: string;
  onEmbeddingModelChange: (value: string) => void;
  onRerankModelChange: (value: string) => void;
  onModeChange: (value: IndexMode) => void;
  onAutoStrategyChange: (value: IndexAutoStrategy) => void;
  onEnabledProjectsChange: (projectIds: string[]) => void;
  onChunkSizeChange: (value: string) => void;
  onChunkOverlapChange: (value: string) => void;
  onChunkConfigBlur: () => void;
  isAgentSettingsLocked: boolean;
}

export function IndexSettingsGlobalConfig({
  settings,
  embeddingModelOptions,
  rerankModelOptions,
  projectOptions,
  modeOptions,
  autoStrategyOptions,
  chunkSize,
  chunkOverlap,
  onEmbeddingModelChange,
  onRerankModelChange,
  onModeChange,
  onAutoStrategyChange,
  onEnabledProjectsChange,
  onChunkSizeChange,
  onChunkOverlapChange,
  onChunkConfigBlur,
  isAgentSettingsLocked,
}: IndexSettingsGlobalConfigProps) {
  const { t } = useTranslation();

  return (
    <Box className="index-settings-card">
      <Flex
        direction="column"
        gap="4"
      >
        <IndexSettingsSectionHeader title={t("index.globalSettings")} />
        <Box className="index-settings-global-config__grid">
          <Flex
            direction="column"
            gap="1"
          >
            <Text
              size="1"
              color="gray"
            >
              {t("index.embeddingModel")}
            </Text>
            <ModelIdSelect
              value={settings.defaultEmbeddingModel || ""}
              onChange={onEmbeddingModelChange}
              models={embeddingModelOptions}
              taskType="embedding"
              placeholder={t("index.disabled")}
              editable={false}
              allowCustomValue={false}
              emptyOptionLabel={t("index.disabled")}
              triggerClassName="index-settings-global-config__field"
              disabled={isAgentSettingsLocked}
            />
          </Flex>

          <Flex
            direction="column"
            gap="1"
          >
            <Text
              size="1"
              color="gray"
            >
              {t("index.rerankModel")}
            </Text>
            <ModelIdSelect
              value={settings.indexRerankEnabled ? settings.defaultRerankModel || "" : ""}
              onChange={onRerankModelChange}
              models={rerankModelOptions}
              taskType="rerank"
              placeholder={t("index.disabled")}
              editable={false}
              allowCustomValue={false}
              emptyOptionLabel={t("index.disabled")}
              triggerClassName="index-settings-global-config__field"
              disabled={isAgentSettingsLocked}
            />
          </Flex>

          <LabeledSelect
            label={t("index.enable")}
            value={settings.indexMode}
            options={modeOptions}
            onChange={(value) => onModeChange(value as IndexMode)}
            triggerClassName="index-settings-global-config__field"
            labelSize="1"
            labelWeight="regular"
            labelColor="gray"
            gap="1"
            disabled={isAgentSettingsLocked}
          />

          <LabeledSelect
            label={t("index.autoStrategy")}
            value={settings.indexAutoStrategy}
            options={autoStrategyOptions}
            onChange={(value) => onAutoStrategyChange(value as IndexAutoStrategy)}
            triggerClassName="index-settings-global-config__field"
            labelSize="1"
            labelWeight="regular"
            labelColor="gray"
            gap="1"
            disabled={isAgentSettingsLocked}
          />

          {settings.indexMode === "selected" ? (
            <Box className="index-settings-global-config__full-width">
              <MultiSelectField
                label={t("index.selectProjects")}
                options={projectOptions}
                value={settings.indexEnabledProjects}
                placeholder={t("index.selectProjectsPlaceholder")}
                emptyMessage={t("index.noProjects")}
                triggerClassName="index-settings-global-config__field"
                labelSize="1"
                labelWeight="regular"
                labelColor="gray"
                onChange={onEnabledProjectsChange}
                disabled={isAgentSettingsLocked}
              />
            </Box>
          ) : null}

          <LabeledNumberInput
            label={t("index.chunkSize")}
            value={chunkSize}
            min={1}
            unit={t("index.unitCharacters")}
            onChange={onChunkSizeChange}
            onBlur={onChunkConfigBlur}
            disabled={isAgentSettingsLocked}
          />
          <LabeledNumberInput
            label={t("index.chunkOverlap")}
            value={chunkOverlap}
            min={0}
            unit={t("index.unitCharacters")}
            onChange={onChunkOverlapChange}
            onBlur={onChunkConfigBlur}
            disabled={isAgentSettingsLocked}
          />
        </Box>
      </Flex>
    </Box>
  );
}

function LabeledNumberInput({
  label,
  value,
  min,
  unit,
  onChange,
  onBlur,
  disabled,
}: {
  label: string;
  value: string;
  min: number;
  unit: string;
  onChange: (value: string) => void;
  onBlur: () => void;
  disabled: boolean;
}) {
  return (
    <Flex
      direction="column"
      gap="1"
    >
      <Text
        size="1"
        color="gray"
      >
        {label}
      </Text>
      <UnitTextField
        type="number"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onBlur={onBlur}
        min={min}
        unit={unit}
        unitSide="right"
        disabled={disabled}
      />
    </Flex>
  );
}
