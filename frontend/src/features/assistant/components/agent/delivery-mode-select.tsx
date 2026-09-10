import { DropdownMenu, Button } from "@radix-ui/themes";
import { CornerDownRight, ListOrdered, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { AgentDeliveryMode } from "@/lib/agent.types";

export function DeliveryModeSelect({
  value,
  onChange,
}: {
  value: AgentDeliveryMode;
  onChange: (value: AgentDeliveryMode) => void;
}) {
  const { t } = useTranslation();
  const Icon = value === "queue" ? ListOrdered : CornerDownRight;
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger>
        <Button
          variant="ghost"
          size="1"
          color="gray"
          aria-label={t(value === "queue" ? "assistant.deliveryQueue" : "assistant.deliverySteer")}
          title={t(
            value === "queue" ? "assistant.deliveryQueueHint" : "assistant.deliverySteerHint",
          )}
        >
          <Icon size={14} />
          <ChevronDown size={12} />
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Content size="1">
        <DropdownMenu.RadioGroup
          value={value}
          onValueChange={(mode) => onChange(mode as AgentDeliveryMode)}
        >
          <DropdownMenu.RadioItem value="steer">
            {t("assistant.deliverySteer")}
          </DropdownMenu.RadioItem>
          <DropdownMenu.RadioItem value="queue">
            {t("assistant.deliveryQueue")}
          </DropdownMenu.RadioItem>
        </DropdownMenu.RadioGroup>
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
}
