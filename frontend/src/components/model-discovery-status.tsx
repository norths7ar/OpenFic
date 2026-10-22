import { Badge, Text, Tooltip } from "@radix-ui/themes";
import { AlertTriangle, CloudOff } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { ModelDiscoveryFields } from "@/lib/model.types";

export function ModelDiscoveryStatus({
  model,
  compact = false,
}: {
  model: ModelDiscoveryFields;
  compact?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const failed = model.discoveryStatus === "error";
  if (!failed && model.upstreamStatus !== "not_listed") return null;

  const label = t(failed ? "models.discoveryFailed" : "models.upstreamNotListed");
  const hint = t(failed ? "models.discoveryFailedHint" : "models.upstreamNotListedHint");
  const checkedAt = model.discoveryCheckedAt ? new Date(model.discoveryCheckedAt) : null;
  const lastChecked =
    checkedAt && Number.isFinite(checkedAt.getTime())
      ? t("models.lastDiscovered", { time: checkedAt.toLocaleString(i18n.language) })
      : "";
  const Icon = failed ? CloudOff : AlertTriangle;

  return (
    <Tooltip content={[hint, lastChecked].filter(Boolean).join(" ")}>
      {compact ? (
        <Text
          as="span"
          color={failed ? "gray" : "amber"}
          aria-label={label}
          role="img"
        >
          <Icon
            size={14}
            aria-hidden="true"
          />
        </Text>
      ) : (
        <Badge
          color={failed ? "gray" : "amber"}
          variant="soft"
        >
          <Icon
            size={12}
            aria-hidden="true"
          />
          {label}
        </Badge>
      )}
    </Tooltip>
  );
}
