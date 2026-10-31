import { Box, Flex, IconButton, Tooltip } from "@radix-ui/themes";
import { PanelLeft } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import type { KeyboardEvent, PointerEvent } from "react";

import "./sidebar-brand.css";

import {
  SIDEBAR_EXPANDED_WIDTH,
  SIDEBAR_ICON_SIZE,
  SIDEBAR_ITEM_HEIGHT,
} from "./app-sidebar.constants";

const MotionFlex = motion.create(Flex);

interface SidebarBrandProps {
  isExpanded: boolean;
  isHovered: boolean;
  expandLabel: string;
  projectsLabel: string;
  collapseLabel: string;
  onToggleExpanded: () => void;
  onNavigateHome: () => void;
  onPointerEnter: () => void;
  onPointerLeave: () => void;
  onPointerMove: (event: PointerEvent<HTMLDivElement>) => void;
}

export function SidebarBrand({
  isExpanded,
  isHovered,
  expandLabel,
  projectsLabel,
  collapseLabel,
  onToggleExpanded,
  onNavigateHome,
  onPointerEnter,
  onPointerLeave,
  onPointerMove,
}: SidebarBrandProps) {
  const handleActivate = () => {
    if (isExpanded) {
      onNavigateHome();
    } else {
      onToggleExpanded();
    }
  };

  return (
    <Flex
      align="center"
      gap="0"
      className="sidebar-brand__slot"
    >
      <MotionFlex
        align="center"
        onPointerEnter={onPointerEnter}
        onPointerLeave={onPointerLeave}
        onPointerMove={onPointerMove}
        onClick={handleActivate}
        role="button"
        tabIndex={0}
        aria-label={isExpanded ? projectsLabel : expandLabel}
        onKeyDown={(event: KeyboardEvent<HTMLDivElement>) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            handleActivate();
          }
        }}
        animate={{
          width: isExpanded ? SIDEBAR_EXPANDED_WIDTH - 72 : SIDEBAR_ITEM_HEIGHT,
        }}
        className="sidebar-brand__brand-action"
        style={{
          width: isExpanded ? SIDEBAR_EXPANDED_WIDTH - 72 : SIDEBAR_ITEM_HEIGHT,
          backgroundColor: !isExpanded && isHovered ? "var(--gray-a3)" : "transparent",
        }}
        transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
        whileTap={{ scale: 0.97 }}
      >
        <div className="sidebar-brand-collapsed">
          <AnimatePresence
            mode="wait"
            initial={false}
          >
            {!isExpanded && isHovered ? (
              <motion.div
                key="panel"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.1 }}
                className="sidebar-brand__actions"
              >
                <PanelLeft
                  size={SIDEBAR_ICON_SIZE}
                  color="currentColor"
                  className="sidebar-brand__active-icon"
                />
              </motion.div>
            ) : (
              <motion.div
                key="logo"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.1 }}
                className="sidebar-brand__actions"
              >
                <span
                  className="sidebar-brand-logo"
                  aria-hidden="true"
                />
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <motion.div
          className="sidebar-brand-wordmark-wrapper"
          initial={false}
          animate={{ opacity: isExpanded ? 1 : 0 }}
          transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
          aria-hidden={!isExpanded}
        >
          <span
            className="sidebar-brand-wordmark"
            aria-hidden="true"
          />
        </motion.div>
      </MotionFlex>

      {isExpanded && (
        <Box
          ml="auto"
          className="sidebar-brand__slot"
        >
          <Tooltip content={collapseLabel}>
            <IconButton
              variant="ghost"
              size="2"
              onClick={onToggleExpanded}
              aria-label={collapseLabel}
              className="sidebar-brand__collapse-action"
            >
              <PanelLeft
                size={SIDEBAR_ICON_SIZE}
                color="currentColor"
              />
            </IconButton>
          </Tooltip>
        </Box>
      )}
    </Flex>
  );
}
