import { QueryClient, type QueryKey } from "@tanstack/react-query";
import { beforeEach, expect, it, vi } from "vitest";

import type { DocumentType, NoteTreeResponse, NoteUpdate } from "@/lib/note.types";

import { useNoteTree, useUpdateNote } from "./use-notes";

let client: QueryClient;
vi.mock("@tanstack/react-query", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@tanstack/react-query")>()),
  useQueryClient: () => client,
  useQuery: (options: unknown) => options,
  useMutation: (options: unknown) => options,
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@/components", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock("../lib/note-api", () => ({}));

beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

it.each<DocumentType>(["note", "outline"])(
  "optimistically updates and rolls back the %s query actually used by the list",
  async (documentType) => {
    const query = useNoteTree("p", documentType) as unknown as { queryKey: QueryKey };
    const initial: NoteTreeResponse = {
      categories: [],
      totalNotes: 1,
      rootNotes: [
        {
          id: "n",
          projectId: "p",
          categoryId: null,
          documentType,
          title: "Title",
          order: 0,
          isLocked: false,
          agentVisibility: "all",
          createdAt: "",
          updatedAt: "",
        },
      ],
    };
    client.setQueryData(query.queryKey, initial);
    const mutation = useUpdateNote("p", documentType) as unknown as {
      onMutate: (input: {
        noteId: string;
        data: NoteUpdate;
      }) => Promise<{ previous: NoteTreeResponse }>;
      onError: (
        error: unknown,
        variables: unknown,
        context: { previous: NoteTreeResponse },
      ) => void;
    };
    const variables = { noteId: "n", data: { agentVisibility: "global" } };
    const context = await mutation.onMutate(variables);
    expect(
      client.getQueryData<NoteTreeResponse>(query.queryKey)?.rootNotes[0]?.agentVisibility,
    ).toBe("global");
    mutation.onError(new Error("save failed"), variables, context);
    expect(
      client.getQueryData<NoteTreeResponse>(query.queryKey)?.rootNotes[0]?.agentVisibility,
    ).toBe("all");
    client.clear();
  },
);
