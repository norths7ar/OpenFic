const AUTO_SCROLL_EDGE_THRESHOLD = 56;
const AUTO_SCROLL_MAX_SPEED = 18;
export { PROJECT_NAV_ITEM_HEIGHT as ENTRY_LIST_ITEM_HEIGHT } from "@/features/project-navigation/lib/project-nav-layout";
import { PROJECT_NAV_ITEM_HEIGHT as ENTRY_LIST_ITEM_HEIGHT } from "@/features/project-navigation/lib/project-nav-layout";

interface AutoScrollPosition {
  containerTop: number;
  containerBottom: number;
  itemTop: number;
  itemBottom: number;
}

interface DragTargetPosition {
  containerTop: number;
  scrollTop: number;
  clientY: number;
  itemCount: number;
}

interface SortableEntry {
  id: string;
  order: number;
  folderId?: string | null;
}

interface EntryDragOffsetPosition {
  entryIndex: number;
  activeIndex: number;
  targetIndex: number;
}

interface DragVisibilityState {
  isDragSource: boolean;
}

export function getAutoScrollSpeed({
  containerTop,
  containerBottom,
  itemTop,
  itemBottom,
}: AutoScrollPosition): number {
  const distanceToTop = itemTop - containerTop;
  if (distanceToTop < AUTO_SCROLL_EDGE_THRESHOLD) {
    const ratio = (AUTO_SCROLL_EDGE_THRESHOLD - distanceToTop) / AUTO_SCROLL_EDGE_THRESHOLD;
    return -Math.max(4, Math.round(AUTO_SCROLL_MAX_SPEED * ratio));
  }

  const distanceToBottom = containerBottom - itemBottom;
  if (distanceToBottom < AUTO_SCROLL_EDGE_THRESHOLD) {
    const ratio = (AUTO_SCROLL_EDGE_THRESHOLD - distanceToBottom) / AUTO_SCROLL_EDGE_THRESHOLD;
    return Math.max(4, Math.round(AUTO_SCROLL_MAX_SPEED * ratio));
  }

  return 0;
}

export function getDragTargetIndex({
  containerTop,
  scrollTop,
  clientY,
  itemCount,
}: DragTargetPosition): number {
  if (itemCount <= 1) return 0;

  const index = Math.floor((scrollTop + clientY - containerTop) / ENTRY_LIST_ITEM_HEIGHT);
  return Math.max(0, Math.min(index, itemCount - 1));
}

export function reorderEntries<T extends SortableEntry>(
  entries: T[],
  activeId: string,
  newIndex: number,
): T[] | null {
  const oldIndex = entries.findIndex((entry) => entry.id === activeId);
  if (oldIndex === -1 || oldIndex === newIndex) return null;
  const active = entries[oldIndex];
  const target = entries[newIndex];
  if (!target || target.folderId !== active.folderId) return null;

  const siblings = entries.filter((entry) => entry.folderId === active.folderId);
  const oldSiblingIndex = siblings.findIndex((entry) => entry.id === activeId);
  const newSiblingIndex = siblings.findIndex((entry) => entry.id === target.id);
  const [movedEntry] = siblings.splice(oldSiblingIndex, 1);
  siblings.splice(newSiblingIndex, 0, movedEntry);

  // Rotate existing sibling order slots, preserving zero-based/gapped orders and other folders.
  let siblingIndex = 0;
  return entries.map((entry) =>
    entry.folderId === active.folderId
      ? { ...siblings[siblingIndex++], order: entry.order }
      : entry,
  );
}

/** The move API accepts a one-based position within the entry's current folder, not an order value. */
export function getEntryMovePosition<T extends SortableEntry>(
  entries: T[],
  entryId: string,
): number {
  const entry = entries.find((item) => item.id === entryId);
  return (
    entries
      .filter((item) => item.folderId === entry?.folderId)
      .findIndex((item) => item.id === entryId) + 1
  );
}

export function getEntryDragOffset({
  entryIndex,
  activeIndex,
  targetIndex,
}: EntryDragOffsetPosition): number {
  if (entryIndex === activeIndex || activeIndex === targetIndex) return 0;

  if (activeIndex < targetIndex && entryIndex > activeIndex && entryIndex <= targetIndex) {
    return -ENTRY_LIST_ITEM_HEIGHT;
  }

  if (activeIndex > targetIndex && entryIndex >= targetIndex && entryIndex < activeIndex) {
    return ENTRY_LIST_ITEM_HEIGHT;
  }

  return 0;
}

export function shouldHideDraggedEntry({ isDragSource }: DragVisibilityState): boolean {
  return isDragSource;
}

export function getEntryListTransition(isDragActive: boolean): string {
  if (isDragActive) {
    return "transform 0.14s ease, background-color 0.08s ease, color 0.08s ease";
  }
  return "background-color 0.08s ease, color 0.08s ease";
}
