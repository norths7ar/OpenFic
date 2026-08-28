export type SceneDraftContextMode = "global" | "local";

export interface SceneDraftTarget {
  chapterId: string;
  chapterTitle: string;
  baseUpdatedAt: string;
  contextMode: SceneDraftContextMode;
}

export interface SceneDraftRequest extends SceneDraftTarget {
  prompt: string;
}

export interface SceneDraftApplyRequest extends SceneDraftTarget {
  content: string;
}
