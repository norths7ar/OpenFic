import { IconButton, Tooltip } from "@radix-ui/themes";
import {
  AtSign,
  AlignLeft,
  ArrowDown,
  ArrowUp,
  FilePlus,
  MoreHorizontal,
  Pencil,
  Trash2,
} from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { ContextMenu, type ContextMenuItem } from "@/components";
import { buildVolumeMentionTag } from "@/features/assistant/lib/mention-text";
import { ProjectNavGroupHeader } from "@/features/project-navigation/components/project-nav-group-header";
import type { VolumeWithChapters } from "@/lib/chapter.types";

interface VolumeHeaderProps {
  volume: VolumeWithChapters;
  isExpanded: boolean;
  isRenaming: boolean;
  isFirst: boolean;
  isLast: boolean;
  canDelete?: boolean;
  isAgentLocked?: boolean;
  onToggle: () => void;
  onStartRename: () => void;
  onRenameConfirm: (title: string) => void;
  onRenameCancel: () => void;
  onEditDescription: () => void;
  onCreateChapter: () => void;
  onAddToConversation?: (markup: string) => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onDelete: () => void;
  onLockedAction?: () => void;
}

export function VolumeHeader({
  volume,
  isExpanded,
  isRenaming,
  isFirst,
  isLast,
  canDelete = true,
  isAgentLocked = false,
  onToggle,
  onStartRename,
  onRenameConfirm,
  onRenameCancel,
  onEditDescription,
  onCreateChapter,
  onAddToConversation,
  onMoveUp,
  onMoveDown,
  onDelete,
  onLockedAction,
}: VolumeHeaderProps) {
  const { t } = useTranslation();
  const [contextMenuPos, setContextMenuPos] = useState<{ x: number; y: number } | null>(null);

  const openMenu = useCallback(
    (position: { x: number; y: number }) => {
      if (isAgentLocked) {
        onLockedAction?.();
        return;
      }
      setContextMenuPos(position);
    },
    [isAgentLocked, onLockedAction],
  );

  const menuItems = useMemo<ContextMenuItem[]>(() => {
    const items: ContextMenuItem[] = [
      {
        id: "rename",
        label: t("volume.menu.rename"),
        icon: Pencil,
        onClick: onStartRename,
      },
      {
        id: "editDescription",
        label: t("volume.menu.editDescription"),
        icon: AlignLeft,
        onClick: onEditDescription,
      },
      {
        id: "newChapter",
        label: t("volume.menu.newChapter"),
        icon: FilePlus,
        onClick: onCreateChapter,
      },
      {
        id: "addToConversation",
        label: t("volume.menu.addToConversation"),
        icon: AtSign,
        disabled: !onAddToConversation,
        onClick: () =>
          onAddToConversation?.(
            buildVolumeMentionTag({
              volumeId: volume.id,
              label: volume.title.trim() || t("volume.untitled"),
            }),
          ),
      },
      {
        id: "sort",
        label: t("writing.sort"),
        onClick: () => {},
        children: [
          {
            id: "moveUp",
            label: t("volume.menu.moveUp"),
            icon: ArrowUp,
            disabled: isFirst,
            onClick: onMoveUp,
          },
          {
            id: "moveDown",
            label: t("volume.menu.moveDown"),
            icon: ArrowDown,
            disabled: isLast,
            onClick: onMoveDown,
          },
        ],
      },
    ];

    if (canDelete) {
      items.push({
        id: "delete",
        label: t("volume.menu.delete"),
        icon: Trash2,
        danger: true,
        onClick: onDelete,
      });
    }

    return items;
  }, [
    canDelete,
    isFirst,
    isLast,
    onCreateChapter,
    onAddToConversation,
    onDelete,
    onEditDescription,
    onMoveDown,
    onMoveUp,
    onStartRename,
    volume.id,
    volume.title,
    t,
  ]);

  // Virtuoso requires a measurable slot, even for a root collection with no header.
  if (volume.isRoot)
    return (
      <div
        aria-hidden
        style={{ height: 1 }}
      />
    );

  return (
    <>
      <ProjectNavGroupHeader
        title={volume.title || t("volume.untitled")}
        description={volume.description}
        count={volume.chapterCount}
        isExpanded={isExpanded}
        isRenaming={isRenaming}
        onToggle={onToggle}
        onRenameConfirm={onRenameConfirm}
        onRenameCancel={onRenameCancel}
        onContextMenu={(event) => {
          event.preventDefault();
          openMenu({ x: event.clientX, y: event.clientY });
        }}
        actions={
          <Tooltip content={t("volume.menu.moreActions")}>
            <IconButton
              variant="ghost"
              color="gray"
              size="1"
              onClick={(event) => {
                event.stopPropagation();
                const rect = event.currentTarget.getBoundingClientRect();
                openMenu({ x: rect.left, y: rect.bottom + 4 });
              }}
              aria-label={t("volume.menu.moreActions")}
            >
              <MoreHorizontal size={15} />
            </IconButton>
          </Tooltip>
        }
      />

      <ContextMenu
        position={contextMenuPos}
        items={menuItems}
        onClose={() => setContextMenuPos(null)}
      />
    </>
  );
}
