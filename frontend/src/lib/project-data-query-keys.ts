export const projectDataQueryKeys = {
  notes: {
    trees: ["note-tree"] as const,
    projectTrees: (projectId: string) => ["note-tree", projectId] as const,
    tree: (projectId: string, documentType: "note" | "outline" = "note") =>
      ["note-tree", projectId, documentType] as const,
    details: ["note"] as const,
    detail: (noteId: string | null) => ["note", noteId] as const,
  },
  characters: {
    lists: ["characters"] as const,
    list: (projectId: string | null) => ["characters", projectId] as const,
    details: ["character"] as const,
    detail: (characterId: string) => ["character", characterId] as const,
    loadedDetail: (characterId: string | null, loadVersion: number) =>
      ["character", characterId, loadVersion] as const,
    search: (projectId: string, query: string) => ["characters-search", projectId, query] as const,
  },
  worldInfo: {
    byProjects: ["world-info-by-project"] as const,
    byProject: (projectId: string | null) => ["world-info-by-project", projectId] as const,
    entriesLists: ["world-info-entries"] as const,
    entries: (worldInfoId: string | null) => ["world-info-entries", worldInfoId] as const,
    entryDetails: ["world-info-entry-detail"] as const,
    entryDetail: (entryId: string | null) => ["world-info-entry-detail", entryId] as const,
    search: (worldInfoId: string, query: string) =>
      ["world-info-entries-search", worldInfoId, query] as const,
  },
};
