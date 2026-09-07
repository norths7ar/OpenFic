import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import { restrictToVerticalAxis } from "@dnd-kit/modifiers";
import { SortableContext, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  Box,
  Button,
  Checkbox,
  Dialog,
  DropdownMenu,
  Flex,
  IconButton,
  Skeleton,
  Switch,
  Text,
  Tooltip,
  TextField,
} from "@radix-ui/themes";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  BotOff,
  CheckSquare,
  ListChecks,
  Pencil,
  Plus,
  Search,
  GripVertical,
  Trash2,
  UserRound,
  FolderInput,
  FolderPlus,
  MoreHorizontal,
} from "lucide-react";
import { motion } from "motion/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { ContextMenu, type ContextMenuItem } from "@/components/context-menu";
import {
  useProjectFolderMutations,
  useProjectFolders,
} from "@/features/project-folders/hooks/use-project-folders";
import type { ProjectFolder } from "@/features/project-folders/lib/project-folder-api";
import { ProjectFolderGroups } from "@/features/project-navigation/components/project-folder-groups";
import { ProjectNavItemRow } from "@/features/project-navigation/components/project-nav-item-row";
import { ProjectNavToolbar } from "@/features/project-navigation/components/project-nav-toolbar";

import "@/features/project-navigation/components/project-nav.css";
import type { CharacterListItem } from "@/lib/character.types";
import { formatRelativeTime } from "@/lib/time-utils";

import { CharacterSearchPopover } from "./character-search-popover";

function CharacterListRow({
  character,
  isSelected,
  isChecked,
  isMultiSelect,
  showDragHandle,
  onSelect,
  onCheck,
  onToggleWritingVisibility,
  onContextMenu,
  t,
}: {
  character: CharacterListItem;
  isSelected: boolean;
  isChecked: boolean;
  isMultiSelect: boolean;
  showDragHandle: boolean;
  onSelect: () => void;
  onCheck: () => void;
  onToggleWritingVisibility: () => void;
  onContextMenu: (event: React.MouseEvent) => void;
  t: (key: string) => string;
}) {
  const { attributes, listeners, setNodeRef, isDragging, transform, transition } = useSortable({
    id: character.id,
    disabled: !showDragHandle,
  });
  return (
    <Box
      ref={setNodeRef}
      role="button"
      tabIndex={0}
      onClick={isMultiSelect ? onCheck : onSelect}
      onKeyDown={(event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        (isMultiSelect ? onCheck : onSelect)();
      }}
      onContextMenu={onContextMenu}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.4 : 1,
      }}
    >
      <ProjectNavItemRow
        selected={isSelected}
        dragging={isDragging}
        title={character.name}
        metadata={
          <>
            <span>
              {character.tokenCount} {t("characters.tokenCount")}
            </span>
            <span>· {formatRelativeTime(character.updatedAt)}</span>
          </>
        }
        leading={
          isMultiSelect ? (
            <Flex
              className="characters-list-leading"
              align="center"
              justify="center"
              onClick={(e) => e.stopPropagation()}
            >
              <Checkbox
                checked={isChecked}
                onCheckedChange={onCheck}
                size="1"
              />
            </Flex>
          ) : showDragHandle ? (
            <Flex
              {...attributes}
              {...listeners}
              className="characters-list-leading characters-list-drag-handle"
              align="center"
              justify="center"
              onClick={(e) => e.stopPropagation()}
              aria-label={t("characters.reorderHandle")}
            >
              <GripVertical size={16} />
            </Flex>
          ) : null
        }
        actions={
          <Tooltip
            content={
              character.isWritingVisible
                ? t("characters.visibleToWritingAgent")
                : t("characters.notVisibleToWritingAgent")
            }
          >
            <span onClick={(e) => e.stopPropagation()}>
              <Switch
                size="1"
                color="green"
                checked={character.isWritingVisible}
                aria-label={
                  character.isWritingVisible
                    ? t("characters.visibleToWritingAgent")
                    : t("characters.notVisibleToWritingAgent")
                }
                onCheckedChange={onToggleWritingVisibility}
              />
            </span>
          </Tooltip>
        }
      />
    </Box>
  );
}

interface CharacterListProps {
  characters: CharacterListItem[];
  projectId: string;
  selectedCharacterId: string | null;
  isLoading?: boolean;
  isCreating?: boolean;
  onCreateCharacter: (folderId?: string) => void;
  onSelectCharacter: (characterId: string) => void;
  onEditProfile: (character: CharacterListItem) => void;
  onDeleteCharacter: (character: CharacterListItem) => void;
  onToggleWritingVisibility: (character: CharacterListItem, isWritingVisible: boolean) => void;
  onBatchDelete: (characterIds: string[]) => void;
  onReorderCharacters: (orderedIds: string[]) => void;
}

interface MenuPosition {
  x: number;
  y: number;
}

type SortField = "order" | "updatedAt" | "tokenCount" | "name";
type SortDirection = "asc" | "desc";

export function CharacterList({
  characters,
  projectId,
  selectedCharacterId,
  isLoading = false,
  isCreating = false,
  onCreateCharacter,
  onSelectCharacter,
  onEditProfile,
  onDeleteCharacter,
  onToggleWritingVisibility,
  onBatchDelete,
  onReorderCharacters,
}: CharacterListProps) {
  const { t } = useTranslation();
  const [menuPosition, setMenuPosition] = useState<MenuPosition | null>(null);
  const [menuCharacterId, setMenuCharacterId] = useState<string | null>(null);
  const [isMultiSelect, setIsMultiSelect] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [batchDeleteDialogOpen, setBatchDeleteDialogOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchExpanded, setSearchExpanded] = useState(false);
  const [sortField, setSortField] = useState<SortField>("order");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [activeCharacterId, setActiveCharacterId] = useState<string | null>(null);
  const searchContainerRef = useRef<HTMLDivElement | null>(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));
  const { data: folders = [] } = useProjectFolders(projectId, "character");
  const shouldShowDragHandle =
    folders.length === 0 && !isMultiSelect && sortField === "order" && sortDirection === "asc";
  const folderMutations = useProjectFolderMutations(projectId, "character");
  const [folderDialog, setFolderDialog] = useState<{
    mode: "create" | "rename";
    folder?: ProjectFolder;
  } | null>(null);
  const [folderTitle, setFolderTitle] = useState("");
  const [deletingFolderId, setDeletingFolderId] = useState<string | null>(null);
  const [folderDescription, setFolderDescription] = useState("");

  const sortedCharacters = useMemo(() => {
    return [...characters].sort((a, b) => {
      let comparison = 0;
      switch (sortField) {
        case "order":
          comparison = a.order - b.order || a.name.localeCompare(b.name, "zh-CN");
          break;
        case "updatedAt":
          comparison = a.updatedAt.localeCompare(b.updatedAt);
          break;
        case "tokenCount":
          comparison = a.tokenCount - b.tokenCount;
          break;
        case "name":
          comparison = a.name.localeCompare(b.name, "zh-CN");
          break;
      }
      return sortDirection === "asc" ? comparison : -comparison;
    });
  }, [characters, sortDirection, sortField]);

  useEffect(() => {
    if (searchExpanded && searchContainerRef.current) {
      const input = searchContainerRef.current.querySelector("input");
      input?.focus();
    }
  }, [searchExpanded]);

  const menuCharacter = useMemo(
    () => characters.find((character) => character.id === menuCharacterId) ?? null,
    [characters, menuCharacterId],
  );

  const handleCloseContextMenu = useCallback(() => {
    setMenuPosition(null);
    setMenuCharacterId(null);
  }, []);

  const handleContextMenu = useCallback(
    (event: React.MouseEvent, character: CharacterListItem) => {
      event.preventDefault();
      setMenuCharacterId(character.id);
      if (isMultiSelect) {
        setSelectedIds((prev) => {
          if (prev.has(character.id)) return prev;
          const next = new Set(prev);
          next.add(character.id);
          return next;
        });
      }
      setMenuPosition({ x: event.clientX, y: event.clientY });
    },
    [isMultiSelect],
  );

  const handleToggleMultiSelect = useCallback(() => {
    setIsMultiSelect((prev) => {
      if (prev) setSelectedIds(new Set());
      return !prev;
    });
  }, []);

  const handleCheckCharacter = useCallback((characterId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(characterId)) {
        next.delete(characterId);
      } else {
        next.add(characterId);
      }
      return next;
    });
  }, []);

  const handleSelectAll = useCallback(() => {
    setSelectedIds(new Set(sortedCharacters.map((character) => character.id)));
  }, [sortedCharacters]);

  const handleDeselectAll = useCallback(() => {
    setSelectedIds(new Set());
  }, []);

  const handleSortChange = useCallback(
    (field: SortField) => {
      if (sortField === field) {
        setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
        return;
      }
      setSortField(field);
      setSortDirection(field === "order" || field === "name" ? "asc" : "desc");
    },
    [sortField],
  );

  function getSortIcon(field: SortField) {
    if (sortField !== field) return null;
    return sortDirection === "asc" ? <ArrowUp size={12} /> : <ArrowDown size={12} />;
  }

  const handleSearchChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchQuery(event.target.value);
    if (event.target.value.trim()) setSearchOpen(true);
  }, []);

  const handleSearchToggle = useCallback(() => {
    setSearchExpanded((prev) => {
      if (prev) {
        setSearchOpen(false);
        return false;
      }
      return true;
    });
    if (!searchExpanded && searchQuery.trim()) setSearchOpen(true);
  }, [searchExpanded, searchQuery]);

  const handleSearchBlur = useCallback(() => {
    if (!searchQuery.trim()) {
      setSearchExpanded(false);
    }
  }, [searchQuery]);

  const handlePopoverOpenChange = useCallback((open: boolean) => {
    setSearchOpen(open);
    if (!open) setSearchExpanded(false);
  }, []);

  const handleBatchDeleteConfirm = useCallback(() => {
    if (selectedIds.size === 0) return;
    onBatchDelete(Array.from(selectedIds));
    setSelectedIds(new Set());
    setIsMultiSelect(false);
    setBatchDeleteDialogOpen(false);
  }, [onBatchDelete, selectedIds]);

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      setActiveCharacterId(null);
      if (!shouldShowDragHandle || !event.over || event.active.id === event.over.id) return;
      const from = sortedCharacters.findIndex((character) => character.id === event.active.id);
      const to = sortedCharacters.findIndex((character) => character.id === event.over?.id);
      if (from < 0 || to < 0) return;
      const next = [...sortedCharacters];
      const [moved] = next.splice(from, 1);
      next.splice(to, 0, moved);
      onReorderCharacters(next.map((character) => character.id));
    },
    [onReorderCharacters, shouldShowDragHandle, sortedCharacters],
  );

  const handleManualMove = useCallback(
    (direction: -1 | 1) => {
      if (!menuCharacter || sortField !== "order") return;
      const index = sortedCharacters.findIndex((character) => character.id === menuCharacter.id);
      const targetIndex = index + direction;
      if (index < 0 || targetIndex < 0 || targetIndex >= sortedCharacters.length) return;
      const next = [...sortedCharacters];
      const [moved] = next.splice(index, 1);
      next.splice(targetIndex, 0, moved);
      handleCloseContextMenu();
      onReorderCharacters(next.map((character) => character.id));
    },
    [handleCloseContextMenu, menuCharacter, onReorderCharacters, sortField, sortedCharacters],
  );

  const menuItems = useMemo<ContextMenuItem[]>(() => {
    if (isMultiSelect) {
      return [
        {
          id: "delete-selected",
          label: t("characters.deleteSelected"),
          icon: Trash2,
          danger: true,
          onClick: () => setBatchDeleteDialogOpen(true),
        },
      ];
    }

    if (!menuCharacter) return [];

    const manualIndex = sortedCharacters.findIndex(
      (character) => character.id === menuCharacter.id,
    );
    const items: ContextMenuItem[] = [
      {
        id: "edit-profile",
        label: t("characters.editProfile"),
        icon: Pencil,
        onClick: () => {
          handleCloseContextMenu();
          onEditProfile(menuCharacter);
        },
      },
    ];
    if (sortField === "order") {
      items.push(
        {
          id: "move-up",
          label: t("chapterMenu.moveUp"),
          icon: ArrowUp,
          disabled: manualIndex <= 0,
          onClick: () => handleManualMove(-1),
        },
        {
          id: "move-down",
          label: t("chapterMenu.moveDown"),
          icon: ArrowDown,
          disabled: manualIndex < 0 || manualIndex >= sortedCharacters.length - 1,
          onClick: () => handleManualMove(1),
        },
      );
    }
    items.push(
      {
        id: "move-root",
        label: t("projectNavigation.moveToRoot"),
        icon: FolderInput,
        disabled: menuCharacter.folderId === null,
        onClick: () => {
          handleCloseContextMenu();
          folderMutations.moveItem.mutate({ itemId: menuCharacter.id, folderId: null });
        },
      },
      ...folders.map((folder) => ({
        id: `move-folder-${folder.id}`,
        label: t("projectNavigation.moveToFolder", { name: folder.title }),
        icon: FolderInput,
        disabled: menuCharacter.folderId === folder.id,
        onClick: () => {
          handleCloseContextMenu();
          folderMutations.moveItem.mutate({ itemId: menuCharacter.id, folderId: folder.id });
        },
      })),
      {
        id: "writing-visibility",
        label: menuCharacter.isWritingVisible
          ? t("characters.hideFromWritingAgent")
          : t("characters.showToWritingAgent"),
        icon: BotOff,
        onClick: () => {
          handleCloseContextMenu();
          onToggleWritingVisibility(menuCharacter, !menuCharacter.isWritingVisible);
        },
      },
      {
        id: "delete",
        label: t("characters.deleteCharacter"),
        icon: Trash2,
        danger: true,
        onClick: () => {
          handleCloseContextMenu();
          onDeleteCharacter(menuCharacter);
        },
      },
    );
    return items;
  }, [
    handleCloseContextMenu,
    handleManualMove,
    folderMutations.moveItem,
    folders,
    isMultiSelect,
    menuCharacter,
    onDeleteCharacter,
    onEditProfile,
    onToggleWritingVisibility,
    sortField,
    sortedCharacters,
    t,
  ]);

  return (
    <>
      <Flex
        className="characters-list"
        direction="column"
      >
        <Box className="characters-list-header">
          <Flex
            direction="column"
            gap="0"
          >
            <ProjectNavToolbar
              search={
                <Box
                  ref={searchContainerRef}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 0,
                    height: "var(--space-6)",
                    paddingRight: searchExpanded ? "var(--space-2)" : 0,
                    border: "1px solid transparent",
                    borderColor: searchExpanded ? "var(--gray-a7)" : "transparent",
                    borderRadius: "max(var(--radius-2), var(--radius-full))",
                    background: searchExpanded ? "var(--color-surface)" : "transparent",
                    flex: searchExpanded ? 1 : undefined,
                    minWidth: 0,
                    position: "relative",
                    transition:
                      "border-color 0.15s ease, background 0.15s ease, padding-right 0.15s ease",
                  }}
                >
                  <CharacterSearchPopover
                    projectId={projectId}
                    query={searchQuery}
                    open={searchOpen}
                    onOpenChange={handlePopoverOpenChange}
                    onNavigateToMatch={onSelectCharacter}
                  >
                    <Box
                      style={{
                        position: "absolute",
                        inset: 0,
                        pointerEvents: "none",
                      }}
                    />
                  </CharacterSearchPopover>
                  <IconButton
                    variant="ghost"
                    size="2"
                    aria-label={t("characters.search")}
                    onClick={searchExpanded ? undefined : handleSearchToggle}
                    style={{
                      flexShrink: 0,
                      opacity: searchExpanded ? 0.5 : 1,
                      transition: "opacity 0.15s ease",
                      cursor: searchExpanded ? "default" : undefined,
                    }}
                  >
                    <Search size={16} />
                  </IconButton>
                  <motion.div
                    animate={{ width: searchExpanded ? 200 : 0, opacity: searchExpanded ? 1 : 0 }}
                    transition={{ duration: 0.15, ease: "easeOut" }}
                    style={{ overflow: "hidden" }}
                  >
                    <input
                      type="text"
                      value={searchQuery}
                      placeholder={t("characters.searchPlaceholder")}
                      onChange={handleSearchChange}
                      onFocus={() => {
                        if (searchQuery.trim()) setSearchOpen(true);
                      }}
                      onBlur={handleSearchBlur}
                      style={{
                        width: 200,
                        border: "none",
                        outline: "none",
                        background: "transparent",
                        fontSize: "var(--font-size-base)",
                        lineHeight: "var(--line-height-2)",
                        color: "var(--gray-12)",
                        padding: 0,
                      }}
                    />
                  </motion.div>
                </Box>
              }
              sort={
                isMultiSelect ? (
                  <Tooltip
                    content={
                      selectedIds.size > 0 ? t("characters.deselectAll") : t("characters.selectAll")
                    }
                  >
                    <IconButton
                      variant="ghost"
                      size="2"
                      onClick={selectedIds.size > 0 ? handleDeselectAll : handleSelectAll}
                    >
                      <CheckSquare size={16} />
                    </IconButton>
                  </Tooltip>
                ) : (
                  <DropdownMenu.Root>
                    <DropdownMenu.Trigger>
                      <IconButton
                        variant="ghost"
                        size="2"
                        aria-label={t("characters.sort")}
                      >
                        <ArrowUpDown size={16} />
                      </IconButton>
                    </DropdownMenu.Trigger>
                    <DropdownMenu.Content align="end">
                      <DropdownMenu.Item onClick={() => handleSortChange("order")}>
                        <Flex
                          align="center"
                          justify="between"
                          width="100%"
                        >
                          <Text>{t("characters.sortByOrder")}</Text>
                          {getSortIcon("order")}
                        </Flex>
                      </DropdownMenu.Item>
                      <DropdownMenu.Item onClick={() => handleSortChange("updatedAt")}>
                        <Flex
                          align="center"
                          justify="between"
                          width="100%"
                        >
                          <Text>{t("characters.sortByUpdated")}</Text>
                          {getSortIcon("updatedAt")}
                        </Flex>
                      </DropdownMenu.Item>
                      <DropdownMenu.Item onClick={() => handleSortChange("tokenCount")}>
                        <Flex
                          align="center"
                          justify="between"
                          width="100%"
                        >
                          <Text>{t("characters.sortByTokens")}</Text>
                          {getSortIcon("tokenCount")}
                        </Flex>
                      </DropdownMenu.Item>
                      <DropdownMenu.Item onClick={() => handleSortChange("name")}>
                        <Flex
                          align="center"
                          justify="between"
                          width="100%"
                        >
                          <Text>{t("characters.sortByName")}</Text>
                          {getSortIcon("name")}
                        </Flex>
                      </DropdownMenu.Item>
                    </DropdownMenu.Content>
                  </DropdownMenu.Root>
                )
              }
              create={
                <>
                  {isMultiSelect ? (
                    <Tooltip content={t("characters.deleteSelectedTooltip")}>
                      <IconButton
                        variant="ghost"
                        color="red"
                        size="2"
                        disabled={selectedIds.size === 0}
                        onClick={() => setBatchDeleteDialogOpen(true)}
                      >
                        <Trash2 size={16} />
                      </IconButton>
                    </Tooltip>
                  ) : (
                    <Tooltip content={t("characters.newCharacter")}>
                      <IconButton
                        variant="ghost"
                        size="2"
                        disabled={isCreating}
                        onClick={() => onCreateCharacter()}
                      >
                        <Plus size={16} />
                      </IconButton>
                    </Tooltip>
                  )}
                </>
              }
              more={
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
                    {!isMultiSelect ? (
                      <DropdownMenu.Item
                        onClick={() => {
                          setFolderTitle("");
                          setFolderDescription("");
                          setFolderDialog({ mode: "create" });
                        }}
                      >
                        <FolderPlus size={16} />
                        {t("projectNavigation.newFolder")}
                      </DropdownMenu.Item>
                    ) : null}
                    <DropdownMenu.Item onClick={handleToggleMultiSelect}>
                      <ListChecks size={16} />
                      {t(
                        isMultiSelect
                          ? "characters.multiselectExit"
                          : "characters.multiselectEnter",
                      )}
                    </DropdownMenu.Item>
                  </DropdownMenu.Content>
                </DropdownMenu.Root>
              }
            />
          </Flex>
        </Box>

        <Box className="characters-list-body">
          {isLoading ? (
            <Flex
              direction="column"
              gap="0"
            >
              {Array.from({ length: 8 }).map((_, index) => (
                <Box
                  key={index}
                  p="3"
                  style={{ borderBottom: "1px solid var(--gray-a5)" }}
                >
                  <Flex
                    align="center"
                    gap="2"
                    justify="between"
                  >
                    <Skeleton
                      width="32px"
                      height="32px"
                      style={{ borderRadius: 999 }}
                    />
                    <Flex
                      direction="column"
                      gap="1"
                      style={{ flex: 1, minWidth: 0 }}
                    >
                      <Skeleton
                        height="14px"
                        width={`${50 + (index % 4) * 12}%`}
                        style={{ maxWidth: 200 }}
                      />
                      <Skeleton
                        height="12px"
                        width="120px"
                      />
                    </Flex>
                    <Skeleton
                      width="20px"
                      height="20px"
                    />
                  </Flex>
                </Box>
              ))}
            </Flex>
          ) : characters.length === 0 && folders.length === 0 ? (
            <Flex
              className="characters-empty"
              direction="column"
              align="center"
              justify="center"
              gap="2"
              py="6"
            >
              <UserRound size={28} />
              <Text
                size="2"
                color="gray"
              >
                {t("characters.empty")}
              </Text>
              <Button
                size="2"
                variant="soft"
                disabled={isCreating}
                onClick={() => onCreateCharacter()}
              >
                {t("characters.newCharacter")}
              </Button>
            </Flex>
          ) : (
            <Flex
              direction="column"
              width="100%"
              style={{ minWidth: 0 }}
            >
              <DndContext
                sensors={sensors}
                modifiers={[restrictToVerticalAxis]}
                onDragStart={(event) => setActiveCharacterId(String(event.active.id))}
                onDragCancel={() => setActiveCharacterId(null)}
                onDragEnd={handleDragEnd}
              >
                <SortableContext
                  items={sortedCharacters.map((character) => character.id)}
                  strategy={verticalListSortingStrategy}
                >
                  <ProjectFolderGroups
                    folders={folders}
                    items={sortedCharacters}
                    renderFolderMenu={(folder) => (
                      <DropdownMenu.Root>
                        <DropdownMenu.Trigger>
                          <IconButton
                            variant="ghost"
                            size="1"
                            aria-label={t("common.more")}
                          >
                            <MoreHorizontal size={14} />
                          </IconButton>
                        </DropdownMenu.Trigger>
                        <DropdownMenu.Content align="end">
                          <DropdownMenu.Item onClick={() => onCreateCharacter(folder.id)}>
                            {t("characters.newCharacter")}
                          </DropdownMenu.Item>
                          <DropdownMenu.Item
                            onClick={() => {
                              setFolderTitle(folder.title);
                              setFolderDescription(folder.description ?? "");
                              setFolderDialog({ mode: "rename", folder });
                            }}
                          >
                            {t("common.rename")}
                          </DropdownMenu.Item>
                          <DropdownMenu.Item
                            color="red"
                            onClick={() => setDeletingFolderId(folder.id)}
                          >
                            {t("common.delete")}
                          </DropdownMenu.Item>
                        </DropdownMenu.Content>
                      </DropdownMenu.Root>
                    )}
                    renderItem={(character) => {
                      const isSelected = character.id === selectedCharacterId;
                      const isChecked = selectedIds.has(character.id);
                      return (
                        <CharacterListRow
                          key={character.id}
                          character={character}
                          isSelected={isSelected}
                          isChecked={isChecked}
                          isMultiSelect={isMultiSelect}
                          showDragHandle={shouldShowDragHandle}
                          onSelect={() => onSelectCharacter(character.id)}
                          onCheck={() => handleCheckCharacter(character.id)}
                          onToggleWritingVisibility={() =>
                            onToggleWritingVisibility(character, !character.isWritingVisible)
                          }
                          onContextMenu={(event) => handleContextMenu(event, character)}
                          t={t}
                        />
                      );
                    }}
                  />
                </SortableContext>
                <DragOverlay>
                  {activeCharacterId ? (
                    <Box className="characters-list-item">
                      <Text>
                        {characters.find((character) => character.id === activeCharacterId)?.name}
                      </Text>
                    </Box>
                  ) : null}
                </DragOverlay>
              </DndContext>
            </Flex>
          )}
        </Box>
      </Flex>

      <ContextMenu
        position={menuPosition}
        items={menuItems}
        onClose={handleCloseContextMenu}
      />

      <Dialog.Root
        open={batchDeleteDialogOpen}
        onOpenChange={setBatchDeleteDialogOpen}
      >
        <Dialog.Content style={{ maxWidth: 400 }}>
          <Dialog.Title>{t("characters.deleteSelected")}</Dialog.Title>
          <Dialog.Description
            size="2"
            mb="4"
          >
            {t("characters.batchDeleteConfirm", { count: selectedIds.size })}
          </Dialog.Description>
          <Flex
            gap="3"
            justify="end"
          >
            <Dialog.Close>
              <Button
                variant="soft"
                color="gray"
              >
                {t("common.cancel")}
              </Button>
            </Dialog.Close>
            <Button
              variant="solid"
              color="red"
              onClick={handleBatchDeleteConfirm}
            >
              {t("common.delete")}
            </Button>
          </Flex>
        </Dialog.Content>
      </Dialog.Root>

      <ConfirmDialog
        open={deletingFolderId !== null}
        onOpenChange={(open) => {
          if (!open) setDeletingFolderId(null);
        }}
        title={t("common.delete")}
        description={t("projectNavigation.deleteFolderConfirm")}
        onConfirm={() => {
          if (deletingFolderId) folderMutations.remove.mutate(deletingFolderId);
          setDeletingFolderId(null);
        }}
      />
      <Dialog.Root
        open={folderDialog !== null}
        onOpenChange={(open) => {
          if (!open) setFolderDialog(null);
        }}
      >
        <Dialog.Content style={{ maxWidth: 400 }}>
          <Dialog.Title>
            {t(
              folderDialog?.mode === "rename"
                ? "projectNavigation.renameFolder"
                : "projectNavigation.newFolder",
            )}
          </Dialog.Title>
          <TextField.Root
            value={folderTitle}
            onChange={(event) => setFolderTitle(event.target.value)}
            autoFocus
          />
          <textarea
            aria-label={t("volume.menu.editDescription")}
            placeholder={t("volume.menu.editDescription")}
            value={folderDescription}
            onChange={(event) => setFolderDescription(event.target.value)}
            style={{
              width: "100%",
              boxSizing: "border-box",
              marginTop: 12,
              minHeight: 70,
              background: "var(--color-background)",
              color: "var(--gray-12)",
            }}
          />
          <Flex
            gap="3"
            justify="end"
            mt="4"
          >
            <Dialog.Close>
              <Button
                variant="soft"
                color="gray"
              >
                {t("common.cancel")}
              </Button>
            </Dialog.Close>
            <Button
              onClick={() => {
                const title = folderTitle.trim();
                if (!title || !folderDialog) return;
                if (folderDialog.mode === "rename" && folderDialog.folder) {
                  folderMutations.rename.mutate({
                    folderId: folderDialog.folder.id,
                    title,
                    description: folderDescription || null,
                  });
                } else {
                  folderMutations.create.mutate({ title, description: folderDescription || null });
                }
                setFolderDialog(null);
                setFolderTitle("");
                setFolderDescription("");
              }}
            >
              {t("common.confirm")}
            </Button>
          </Flex>
        </Dialog.Content>
      </Dialog.Root>
    </>
  );
}
