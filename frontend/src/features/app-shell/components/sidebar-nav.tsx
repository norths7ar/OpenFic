import { Box, Flex, Text, Tooltip } from "@radix-ui/themes";
import { motion } from "motion/react";
import { Link } from "react-router";

import "./sidebar-nav.css";
import { SIDEBAR_ICON_SIZE, type AppSidebarNavItem } from "./app-sidebar.constants";

const MotionFlex = motion.create(Flex);

interface SidebarNavProps {
  items: AppSidebarNavItem[];
  isExpanded: boolean;
}

function SidebarNavItem({ item, isExpanded }: { item: AppSidebarNavItem; isExpanded: boolean }) {
  const Icon = item.icon;
  const content = (
    <MotionFlex
      align="center"
      className="app-sidebar-nav-item sidebar-nav__item"
      data-active={item.active ? "true" : "false"}
      whileTap={{ scale: 0.97 }}
      transition={{ duration: 0.15 }}
    >
      <Box className="app-sidebar-nav-item__icon-box sidebar-nav__icon">
        <Icon
          size={SIDEBAR_ICON_SIZE}
          color="currentColor"
          className="app-sidebar-nav-item__icon"
        />
      </Box>
      <motion.div
        initial={false}
        animate={{
          opacity: isExpanded ? 1 : 0,
          width: isExpanded ? 132 : 0,
        }}
        transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
        className="app-sidebar-nav-item__label"
        style={{ pointerEvents: isExpanded ? "auto" : "none" }}
      >
        <Text
          size="2"
          weight={item.active ? "bold" : "medium"}
        >
          {item.label}
        </Text>
      </motion.div>
    </MotionFlex>
  );

  const linked = (
    <Link
      to={item.href}
      aria-label={item.label}
      aria-current={item.active ? "page" : undefined}
      className="app-sidebar-nav-link sidebar-nav__link"
    >
      {content}
    </Link>
  );

  return isExpanded ? (
    <Box
      key={item.href}
      width="100%"
    >
      {linked}
    </Box>
  ) : (
    <Tooltip
      key={item.href}
      content={item.label}
      side="right"
    >
      <Box width="100%">{linked}</Box>
    </Tooltip>
  );
}

export function SidebarNav({ items, isExpanded }: SidebarNavProps) {
  return (
    <Flex
      direction="column"
      align="center"
      gap="1"
      width="100%"
    >
      {items.map((item) => (
        <SidebarNavItem
          key={item.href}
          item={item}
          isExpanded={isExpanded}
        />
      ))}
    </Flex>
  );
}
