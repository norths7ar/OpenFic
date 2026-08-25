import { IconButton, Text, Tooltip } from "@radix-ui/themes";
import { Settings } from "lucide-react";
import { motion } from "motion/react";

import {
  SIDEBAR_ICON_COLOR,
  SIDEBAR_ICON_SIZE,
  sidebarActionButtonStyle,
} from "./app-sidebar.constants";

interface SidebarActionsProps {
  isExpanded: boolean;
  settingsLabel: string;
  onOpenSettings: () => void;
}

export function SidebarActions({
  isExpanded,
  settingsLabel,
  onOpenSettings,
}: SidebarActionsProps) {
  const tooltipSide = isExpanded ? "top" : "right";

  return (
      <motion.div
        layout
        transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
      >
        <Tooltip
          content={settingsLabel}
          side={tooltipSide}
        >
          <IconButton
            variant="ghost"
            size="2"
            onClick={onOpenSettings}
            aria-label={settingsLabel}
            style={{
              ...sidebarActionButtonStyle,
              ...(isExpanded ? { width: "100%", justifyContent: "flex-start" } : undefined),
              color: SIDEBAR_ICON_COLOR,
            }}
          >
            <Settings
              size={SIDEBAR_ICON_SIZE}
              color="currentColor"
            />
            {isExpanded && (
              <Text
                size="2"
                weight="medium"
                ml="2"
              >
                {settingsLabel}
              </Text>
            )}
          </IconButton>
        </Tooltip>
      </motion.div>
  );
}
