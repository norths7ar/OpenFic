import type * as schemas from "@/api/generated/models";
import * as http from "@/api/generated/openfic";
import { resolveBackendUrl } from "@/lib/api-transport";
import type {
  Character,
  CharacterCreate,
  CharacterListItem,
  CharacterListResponse,
  CharacterSearchResponse,
  CharacterUpdate,
} from "@/lib/character.types";

function transformCharacter(raw: schemas.CharacterResponse): Character {
  return {
    id: raw.id as string,
    projectId: raw.project_id as string,
    folderId: (raw.folder_id as string | null | undefined) ?? null,
    name: raw.name as string,
    description: (raw.description as string) || "",
    imageUrl: resolveBackendUrl(raw.image_url as string | null | undefined),
    isFavorited: raw.is_favorited as boolean,
    order: raw.order as number,
    agentVisibility: raw.agent_visibility as string,
    createdAt: raw.created_at as string,
    updatedAt: raw.updated_at as string,
  };
}

function transformCharacterListItem(raw: schemas.CharacterListItemResponse): CharacterListItem {
  return {
    id: raw.id as string,
    projectId: raw.project_id as string,
    folderId: (raw.folder_id as string | null | undefined) ?? null,
    name: raw.name as string,
    imageUrl: resolveBackendUrl(raw.image_url as string | null | undefined),
    tokenCount: raw.token_count as number,
    isFavorited: raw.is_favorited as boolean,
    order: raw.order as number,
    agentVisibility: raw.agent_visibility as string,
    createdAt: raw.created_at as string,
    updatedAt: raw.updated_at as string,
  };
}

export async function fetchCharactersByProject(projectId: string): Promise<CharacterListResponse> {
  const response = await http.listProjectCharactersApiV1ProjectsProjectIdCharactersGet(projectId);
  const data = response.data;
  return {
    items: data.items.map(transformCharacterListItem),
    total: data.total,
  };
}

export async function fetchCharacter(characterId: string): Promise<Character> {
  const response = await http.getCharacterApiV1CharactersCharacterIdGet(characterId);
  return transformCharacter(response.data);
}

export async function createCharacter(
  projectId: string,
  data: CharacterCreate,
): Promise<Character> {
  const formData = new FormData();
  formData.append("name", data.name);
  formData.append("description", data.description ?? "");
  if (data.image) formData.append("image", data.image);

  const response = await http.createCharacterApiV1ProjectsProjectIdCharactersPost(
    projectId,
    formData,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return transformCharacter(response.data);
}

export async function updateCharacter(
  characterId: string,
  data: CharacterUpdate,
): Promise<Character> {
  const formData = new FormData();
  if (data.name !== undefined) formData.append("name", data.name);
  if (data.description !== undefined) {
    formData.append("description", data.description);
  }
  if (data.isFavorited !== undefined) {
    formData.append("is_favorited", String(data.isFavorited));
  }
  if (data.agentVisibility !== undefined) {
    formData.append("agent_visibility", String(data.agentVisibility));
  }
  if (data.image) formData.append("image", data.image);

  const response = await http.updateCharacterApiV1CharactersCharacterIdPatch(
    characterId,
    formData,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return transformCharacter(response.data);
}

export async function deleteCharacter(characterId: string): Promise<void> {
  await http.deleteCharacterApiV1CharactersCharacterIdDelete(characterId);
}

export async function batchFavoriteCharacters(
  projectId: string,
  characterIds: string[],
  isFavorited: boolean,
): Promise<number> {
  const response =
    await http.batchFavoriteCharactersApiV1ProjectsProjectIdCharactersBatchFavoritePost(projectId, {
      character_ids: characterIds,
      is_favorited: isFavorited,
    });
  return response.data.updated_count as number;
}

export async function batchDeleteCharacters(
  projectId: string,
  characterIds: string[],
): Promise<number> {
  const response = await http.batchDeleteCharactersApiV1ProjectsProjectIdCharactersBatchDeletePost(
    projectId,
    {
      character_ids: characterIds,
    },
  );
  return response.data.deleted_count as number;
}

export async function reorderCharacters(projectId: string, orderedIds: string[]): Promise<number> {
  const response = await http.reorderProjectCharactersApiV1ProjectsProjectIdCharactersReorderPost(
    projectId,
    {
      ordered_ids: orderedIds,
    },
  );
  return response.data.updated_count as number;
}

export async function searchCharacters(
  projectId: string,
  query: string,
): Promise<CharacterSearchResponse> {
  const response = await http.searchProjectCharactersApiV1ProjectsProjectIdCharactersSearchGet(
    projectId,
    { q: query },
  );
  const data = response.data;
  return {
    results: (data.results ?? []).map((result) => ({
      characterId: result.character_id as string,
      characterName: result.character_name as string,
      matches: (result.matches ?? []).map((match) => ({
        lineNumber: match.line_number as number,
        lineText: match.line_text as string,
      })),
    })),
    totalCharacters: data.total_characters as number,
    totalMatches: data.total_matches as number,
  };
}
