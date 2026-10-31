import type * as schemas from "@/api/generated/models";
import * as http from "@/api/generated/openfic";
import type {
  SkillReferenceDoc,
  SkillReferenceDocCreate,
  SkillReferenceDocUpdate,
} from "@/lib/skill-reference-doc.types";
import type {
  Skill,
  SkillCreate,
  SkillImportResult,
  SkillListParams,
  SkillListResponse,
  SkillUpdate,
} from "@/lib/skill.types";

function transformSkill(raw: schemas.SkillResponse): Skill {
  return {
    id: raw.id as string,
    name: raw.name as string,
    summary: raw.summary as string,
    content: raw.content as string,
    isEnabled: raw.is_enabled as boolean,
    isComplete: raw.is_complete as boolean,
    source: raw.source as "builtin" | "custom",
    createdAt: raw.created_at as string,
    updatedAt: raw.updated_at as string,
  };
}
function transformSkillReferenceDoc(raw: schemas.SkillReferenceDocResponse): SkillReferenceDoc {
  return {
    id: raw.id as string,
    title: raw.title as string,
    content: raw.content as string,
    tokens: raw.tokens as number,
    createdAt: raw.created_at as string,
    updatedAt: raw.updated_at as string,
  };
}
export async function fetchSkills(params?: SkillListParams): Promise<SkillListResponse> {
  const response = await http.listSkillsApiV1SkillsGet({
    page: params?.page ?? 1,
    page_size: params?.pageSize ?? 100,
  });
  const data = response.data;
  return {
    items: data.items.map(transformSkill),
    total: data.total,
    page: data.page,
    pageSize: data.page_size,
  };
}
export async function fetchSkill(skillDbId: string): Promise<Skill> {
  const response = await http.getSkillApiV1SkillsSkillDbIdGet(skillDbId);
  return transformSkill(response.data);
}
export async function createSkill(data: SkillCreate): Promise<Skill> {
  const response = await http.createSkillApiV1SkillsPost({
    name: data.name,
    summary: data.summary,
    content: data.content,
    is_enabled: data.isEnabled ?? false,
  });
  return transformSkill(response.data);
}
export async function importSkill(file: File): Promise<SkillImportResult> {
  const formData = new FormData();
  formData.append("files", file);
  const response = await http.importSkillApiV1SkillsImportPost(formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return {
    skill: transformSkill(response.data.skill),
    referenceDocs: response.data.reference_docs.map(transformSkillReferenceDoc),
    isRecognized: response.data.is_recognized as boolean,
  };
}
export async function updateSkill(skillDbId: string, data: SkillUpdate): Promise<Skill> {
  const response = await http.updateSkillApiV1SkillsSkillDbIdPatch(skillDbId, {
    name: data.name,
    summary: data.summary,
    content: data.content,
    is_enabled: data.isEnabled,
  });
  return transformSkill(response.data);
}
export async function toggleSkill(skillDbId: string): Promise<Skill> {
  const response = await http.toggleSkillApiV1SkillsSkillDbIdTogglePost(skillDbId);
  return transformSkill(response.data);
}
export async function forkSkill(skillDbId: string): Promise<Skill> {
  const response = await http.forkSkillApiV1SkillsSkillDbIdForkPost(skillDbId);
  return transformSkill(response.data);
}
export async function deleteSkill(skillDbId: string): Promise<void> {
  await http.deleteSkillApiV1SkillsSkillDbIdDelete(skillDbId);
}
export async function fetchSkillReferenceDocs(skillDbId: string): Promise<SkillReferenceDoc[]> {
  const response = await http.listReferenceDocsApiV1SkillsSkillDbIdReferenceDocsGet(skillDbId);
  return response.data.map(transformSkillReferenceDoc);
}
export async function createSkillReferenceDoc(
  skillDbId: string,
  data: SkillReferenceDocCreate,
): Promise<SkillReferenceDoc> {
  const response = await http.createReferenceDocApiV1SkillsSkillDbIdReferenceDocsPost(skillDbId, {
    title: data.title,
    content: data.content,
  });
  return transformSkillReferenceDoc(response.data);
}
export async function updateSkillReferenceDoc(
  skillDbId: string,
  docId: string,
  data: SkillReferenceDocUpdate,
): Promise<SkillReferenceDoc> {
  const response = await http.updateReferenceDocApiV1SkillsSkillDbIdReferenceDocsDocIdPatch(
    skillDbId,
    docId,
    {
      title: data.title,
      content: data.content,
    },
  );
  return transformSkillReferenceDoc(response.data);
}
export async function deleteSkillReferenceDoc(skillDbId: string, docId: string): Promise<void> {
  await http.deleteReferenceDocApiV1SkillsSkillDbIdReferenceDocsDocIdDelete(skillDbId, docId);
}
