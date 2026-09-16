import { Flex, Select, Text, TextField } from "@radix-ui/themes";
import { useTranslation } from "react-i18next";

import { useAgentVisibilityCatalog } from "@/hooks/use-agent-visibility-catalog";

export function PendingChangeFields({
  targetType,
  values,
  onChange,
  disabled,
}: {
  targetType: string;
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
  disabled: boolean;
}) {
  const { t } = useTranslation();
  const { data: catalog } = useAgentVisibilityCatalog();
  return (
    <Flex
      className="pending-change-edit-fields"
      gap="3"
      wrap="wrap"
    >
      <label>
        <Text size="1">{t("pendingProjectChanges.titleField")}</Text>
        <TextField.Root
          value={values.title}
          maxLength={200}
          disabled={disabled}
          onChange={(event) => onChange("title", event.target.value)}
        />
      </label>
      {targetType === "world_entry" && (
        <label>
          <Text size="1">{t("pendingProjectChanges.section")}</Text>
          <TextField.Root
            value={values.section}
            maxLength={500}
            disabled={disabled}
            onChange={(event) => onChange("section", event.target.value)}
          />
        </label>
      )}
      {targetType !== "note_category" && (
        <label>
          <Text size="1">{t("pendingProjectChanges.visibilityField")}</Text>
          <Select.Root
            value={values.agent_visibility}
            disabled={disabled}
            onValueChange={(value) => onChange("agent_visibility", value)}
          >
            <Select.Trigger aria-label={t("pendingProjectChanges.visibilityField")} />
            <Select.Content>
              {catalog?.states.map((state) => (
                <Select.Item
                  key={state.value}
                  value={state.value}
                >
                  {state.label}
                </Select.Item>
              ))}
            </Select.Content>
          </Select.Root>
        </label>
      )}
    </Flex>
  );
}
