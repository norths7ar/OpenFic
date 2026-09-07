export const PROJECT_NAV_ROOT_ID = "__project-root__";

/** Root is a location, not a persisted folder. All page adapters share this rule. */
export function projectNavGroups<F extends { id: string }, T>(
  folders: F[],
  items: T[],
  folderId: (item: T) => string | null,
) {
  const root = items.filter((item) => folderId(item) === null);
  return [
    ...(root.length ? [{ folder: null as F | null, items: root, showHeader: false }] : []),
    ...folders.map((folder) => ({
      folder: folder as F | null,
      items: items.filter((item) => folderId(item) === folder.id),
      showHeader: true,
    })),
  ];
}
