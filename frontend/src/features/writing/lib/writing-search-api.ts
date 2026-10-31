import * as http from "@/api/generated/openfic";
import type { DocumentType } from "@/lib/note.types";

export interface HighlightPart {
  lineNumber: number;
  lineText: string;
}

export function transformHighlightParts(
  raw: Array<{ line_number: number; line_text: string }>,
): HighlightPart[] {
  return raw.map((part) => ({
    lineNumber: part.line_number as number,
    lineText: part.line_text as string,
  }));
}

export interface ChapterSearchMatch extends HighlightPart {}

export interface ChapterSearchResultItem {
  chapterId: string;
  chapterTitle: string;
  volumeTitle: string;
  matches: ChapterSearchMatch[];
}

export interface ChapterSearchResponse {
  results: ChapterSearchResultItem[];
  totalChapters: number;
  totalMatches: number;
}

export async function searchChapters(
  projectId: string,
  query: string,
): Promise<ChapterSearchResponse> {
  const response = await http.searchChaptersApiV1ProjectsProjectIdChaptersSearchGet(projectId, {
    q: query,
  });
  const data = response.data;
  return {
    results: (data.results ?? []).map((result) => ({
      chapterId: result.chapter_id as string,
      chapterTitle: result.chapter_title as string,
      volumeTitle: result.volume_title as string,
      matches: transformHighlightParts(result.matches ?? []),
    })),
    totalChapters: data.total_chapters as number,
    totalMatches: data.total_matches as number,
  };
}

export interface NoteSearchMatch extends HighlightPart {}

export interface NoteSearchResultItem {
  noteId: string;
  noteTitle: string;
  categoryPath: string;
  matches: NoteSearchMatch[];
}

export interface NoteSearchResponse {
  results: NoteSearchResultItem[];
  totalNotes: number;
  totalMatches: number;
}

export async function searchNotes(
  projectId: string,
  query: string,
  documentType: DocumentType = "note",
): Promise<NoteSearchResponse> {
  const response = await http.searchNotesApiV1ProjectsProjectIdNotesSearchGet(projectId, {
    q: query,
    document_type: documentType,
  });
  const data = response.data;
  return {
    results: (data.results ?? []).map((result) => ({
      noteId: result.note_id as string,
      noteTitle: result.note_title as string,
      categoryPath: result.category_path as string,
      matches: transformHighlightParts(result.matches ?? []),
    })),
    totalNotes: data.total_notes as number,
    totalMatches: data.total_matches as number,
  };
}
