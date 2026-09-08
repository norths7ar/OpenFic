import { Box, DropdownMenu, IconButton } from "@radix-ui/themes";
import {
  BookPlus,
  BookOpenText,
  Download,
  FilePlus,
  Plus,
  MoreHorizontal,
  Search,
} from "lucide-react";
import { motion } from "motion/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { ProjectNavToolbar } from "@/features/project-navigation/components/project-nav-toolbar";

import { ChapterSearchPopover } from "./chapter-search-popover";

interface SidebarToolbarProps {
  projectId: string;
  onChapterSelect: (chapterId: string) => void;
  onCreateChapter: () => void;
  onCreateVolume: () => void;
  onExport: () => void;
  onOpenSummary?: () => void;
  isAgentLocked?: boolean;
  onLockedAction?: () => void;
}

export function SidebarToolbar({
  projectId,
  onChapterSelect,
  onCreateChapter,
  onCreateVolume,
  onExport,
  onOpenSummary,
  isAgentLocked = false,
  onLockedAction,
}: SidebarToolbarProps) {
  const { t } = useTranslation();
  const [contentSearchOpen, setContentSearchOpen] = useState(false);
  const [contentSearchExpanded, setContentSearchExpanded] = useState(false);
  const [contentSearchQuery, setContentSearchQuery] = useState("");
  const searchContainerRef = useRef<HTMLDivElement | null>(null);

  const handleCreate = () => {
    if (isAgentLocked) {
      onLockedAction?.();
      return;
    }
    onCreateChapter();
  };

  const handleCreateVolume = () => {
    if (isAgentLocked) {
      onLockedAction?.();
      return;
    }
    onCreateVolume();
  };

  const handleContentSearchToggle = useCallback(() => {
    setContentSearchExpanded((prev) => {
      if (prev) {
        setContentSearchOpen(false);
        return false;
      }
      return true;
    });
    if (!contentSearchExpanded && contentSearchQuery.trim()) {
      setContentSearchOpen(true);
    }
  }, [contentSearchExpanded, contentSearchQuery]);

  const handleContentSearchChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setContentSearchQuery(e.target.value);
    if (e.target.value.trim()) {
      setContentSearchOpen(true);
    }
  }, []);

  const handleContentSearchFocus = useCallback(() => {
    if (contentSearchQuery.trim()) {
      setContentSearchOpen(true);
    }
  }, [contentSearchQuery]);

  const handleContentSearchBlur = useCallback(() => {
    if (!contentSearchQuery.trim()) {
      setContentSearchExpanded(false);
    }
  }, [contentSearchQuery]);

  const handlePopoverOpenChange = useCallback((open: boolean) => {
    setContentSearchOpen(open);
    if (!open) {
      setContentSearchExpanded(false);
    }
  }, []);

  useEffect(() => {
    if (contentSearchExpanded && searchContainerRef.current) {
      const input = searchContainerRef.current.querySelector("input");
      input?.focus();
    }
  }, [contentSearchExpanded]);

  const handleNavigateToChapter = useCallback(
    (chapterId: string) => {
      onChapterSelect(chapterId);
    },
    [onChapterSelect],
  );

  return (
    <ProjectNavToolbar
      search={
        <Box
          ref={searchContainerRef}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 0,
            height: "var(--space-6)",
            paddingRight: contentSearchExpanded ? "var(--space-2)" : 0,
            border: "1px solid transparent",
            borderColor: contentSearchExpanded ? "var(--gray-a7)" : "transparent",
            borderRadius: "max(var(--radius-2), var(--radius-full))",
            background: contentSearchExpanded ? "var(--color-surface)" : "transparent",
            flex: contentSearchExpanded ? 1 : undefined,
            minWidth: 0,
            position: "relative",
            transition: "border-color 0.15s ease, background 0.15s ease, padding-right 0.15s ease",
          }}
        >
          <ChapterSearchPopover
            projectId={projectId}
            query={contentSearchQuery}
            open={contentSearchOpen}
            onOpenChange={handlePopoverOpenChange}
            onNavigateToChapter={handleNavigateToChapter}
          >
            <Box
              style={{
                position: "absolute",
                inset: 0,
                pointerEvents: "none",
              }}
            />
          </ChapterSearchPopover>
          <IconButton
            variant="ghost"
            size="2"
            onClick={contentSearchExpanded ? undefined : handleContentSearchToggle}
            style={{
              flexShrink: 0,
              opacity: contentSearchExpanded ? 0.5 : 1,
              transition: "opacity 0.15s ease",
              cursor: contentSearchExpanded ? "default" : undefined,
            }}
          >
            <Search size={16} />
          </IconButton>
          <motion.div
            initial={{ width: 0, opacity: 0 }}
            animate={{
              width: contentSearchExpanded ? "100%" : 0,
              opacity: contentSearchExpanded ? 1 : 0,
            }}
            transition={{ duration: 0.15, ease: "easeOut" }}
            style={{ overflow: "hidden" }}
          >
            {contentSearchExpanded && (
              <input
                type="text"
                placeholder={t("writing.contentSearchPlaceholder")}
                value={contentSearchQuery}
                onChange={handleContentSearchChange}
                onFocus={handleContentSearchFocus}
                onBlur={handleContentSearchBlur}
                style={{
                  width: "100%",
                  border: "none",
                  outline: "none",
                  background: "transparent",
                  fontSize: "var(--font-size-base)",
                  lineHeight: "var(--line-height-2)",
                  color: "var(--gray-12)",
                  padding: 0,
                }}
              />
            )}
          </motion.div>
        </Box>
      }
      create={
        !contentSearchExpanded ? (
          <DropdownMenu.Root>
            <DropdownMenu.Trigger>
              <IconButton
                variant="ghost"
                size="2"
                aria-label={t("common.create")}
              >
                <Plus size={16} />
              </IconButton>
            </DropdownMenu.Trigger>
            <DropdownMenu.Content align="end">
              <DropdownMenu.Item onClick={handleCreate}>
                <FilePlus size={16} />
                {t("writing.newChapter")}
              </DropdownMenu.Item>
              <DropdownMenu.Item onClick={handleCreateVolume}>
                <BookPlus size={16} />
                {t("writing.newVolume")}
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Root>
        ) : null
      }
      more={
        !contentSearchExpanded ? (
          <DropdownMenu.Root>
            <DropdownMenu.Trigger>
              <IconButton
                variant="ghost"
                size="2"
                aria-label={t("common.more")}
              >
                <MoreHorizontal size={16} />
              </IconButton>
            </DropdownMenu.Trigger>
            <DropdownMenu.Content align="end">
              <DropdownMenu.Item onClick={onExport}>
                <Download size={16} />
                {t("writing.chapterExport.open")}
              </DropdownMenu.Item>
              {onOpenSummary && (
                <DropdownMenu.Item onClick={onOpenSummary}>
                  <BookOpenText size={16} />
                  {t("summary.tabs.chapters")}
                </DropdownMenu.Item>
              )}
            </DropdownMenu.Content>
          </DropdownMenu.Root>
        ) : null
      }
    />
  );
}
