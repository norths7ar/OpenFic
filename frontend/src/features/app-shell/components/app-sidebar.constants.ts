import type { LucideIcon } from "lucide-react";

export const SIDEBAR_COLLAPSED_WIDTH = 64;
export const SIDEBAR_EXPANDED_WIDTH = 232;
export const SIDEBAR_ITEM_HEIGHT = 40;
export const SIDEBAR_ICON_SIZE = 20;

export interface AppSidebarNavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  active: boolean;
}
