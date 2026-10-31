import "./sidebar-actions.css";
import { Box, Text, Tooltip } from "@radix-ui/themes";
import { Settings } from "lucide-react";
import { motion } from "motion/react";

import { SIDEBAR_ICON_SIZE } from "./app-sidebar.constants";

interface SidebarActionsProps {
  isExpanded: boolean;
  settingsLabel: string;
  onOpenSettings: () => void;
}

export function SidebarActions({ isExpanded, settingsLabel, onOpenSettings }: SidebarActionsProps) {
  const action = (
    <motion.button
      type="button"
      className="app-sidebar-nav-item app-sidebar-action-button sidebar-actions__item"
      onClick={onOpenSettings}
      aria-label={settingsLabel}
      whileTap={{ scale: 0.97 }}
      transition={{ duration: 0.15 }}
    >
      <Box className="app-sidebar-nav-item__icon-box sidebar-actions__icon">
        <Settings
          size={SIDEBAR_ICON_SIZE}
          color="currentColor"
        />
      </Box>
      <motion.div
        initial={false}
        animate={{ opacity: isExpanded ? 1 : 0, width: isExpanded ? 132 : 0 }}
        transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
        className="app-sidebar-nav-item__label"
        style={{ pointerEvents: isExpanded ? "auto" : "none" }}
      >
        <Text
          size="2"
          weight="medium"
        >
          {settingsLabel}
        </Text>
      </motion.div>
    </motion.button>
  );

  return isExpanded ? (
    action
  ) : (
    <Tooltip
      content={settingsLabel}
      side="right"
    >
      {action}
    </Tooltip>
  );
}
