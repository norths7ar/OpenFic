import { apiClient } from "@/lib/api-transport";
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

function transformSkill(raw: Record<string, unknown>): Skill {
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
function transformSkillReferenceDoc(raw: Record<string, unknown>): SkillReferenceDoc {
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
  const response = await apiClient.get("/skills", {
    params: { page: params?.page ?? 1, page_size: params?.pageSize ?? 100 },
  });
  const data = response.data;
  return {
    items: (data.items as Record<string, unknown>[]).map(transformSkill),
    total: data.total,
    page: data.page,
    pageSize: data.page_size,
  };
}
export async function fetchSkill(skillDbId: string): Promise<Skill> {
  const response = await apiClient.get(`/skills/${skillDbId}`);
  return transformSkill(response.data);
}
export async function createSkill(data: SkillCreate): Promise<Skill> {
  const response = await apiClient.post("/skills", {
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
  const response = await apiClient.post("/skills/import", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return {
    skill: transformSkill(response.data.skill),
    referenceDocs: (response.data.reference_docs as Record<string, unknown>[]).map(
      transformSkillReferenceDoc,
    ),
    isRecognized: response.data.is_recognized as boolean,
  };
}
export async function updateSkill(skillDbId: string, data: SkillUpdate): Promise<Skill> {
  const response = await apiClient.patch(`/skills/${skillDbId}`, {
    name: data.name,
    summary: data.summary,
    content: data.content,
    is_enabled: data.isEnabled,
  });
  return transformSkill(response.data);
}
export async function toggleSkill(skillDbId: string): Promise<Skill> {
  const response = await apiClient.post(`/skills/${skillDbId}/toggle`);
  return transformSkill(response.data);
}
export async function forkSkill(skillDbId: string): Promise<Skill> {
  const response = await apiClient.post(`/skills/${skillDbId}/fork`);
  return transformSkill(response.data);
}
export async function deleteSkill(skillDbId: string): Promise<void> {
  await apiClient.delete(`/skills/${skillDbId}`);
}
export async function fetchSkillReferenceDocs(skillDbId: string): Promise<SkillReferenceDoc[]> {
  const response = await apiClient.get(`/skills/${skillDbId}/reference-docs`);
  return (response.data as Record<string, unknown>[]).map(transformSkillReferenceDoc);
}
export async function createSkillReferenceDoc(
  skillDbId: string,
  data: SkillReferenceDocCreate,
): Promise<SkillReferenceDoc> {
  const response = await apiClient.post(`/skills/${skillDbId}/reference-docs`, {
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
  const response = await apiClient.patch(`/skills/${skillDbId}/reference-docs/${docId}`, {
    title: data.title,
    content: data.content,
  });
  return transformSkillReferenceDoc(response.data);
}
export async function deleteSkillReferenceDoc(skillDbId: string, docId: string): Promise<void> {
  await apiClient.delete(`/skills/${skillDbId}/reference-docs/${docId}`);
}
