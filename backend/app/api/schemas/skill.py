"""Skill API Schemas。"""

from datetime import datetime

from pydantic import ConfigDict, Field

from app.api.schemas.base import APIModel
from app.api.schemas.skill_reference_doc import SkillReferenceDocResponse


class SkillCreate(APIModel):
    name: str = Field(default="", description="技能名称")
    summary: str = Field(default="", description="技能简述")
    content: str = Field(default="", description="技能内容")
    is_enabled: bool = Field(default=False, description="是否启用")


class SkillUpdate(APIModel):
    name: str | None = Field(default=None, description="技能名称")
    summary: str | None = Field(default=None, description="技能简述")
    content: str | None = Field(default=None, description="技能内容")
    is_enabled: bool | None = Field(default=None, description="是否启用")


class SkillResponse(APIModel):
    id: str
    name: str
    summary: str
    content: str
    is_enabled: bool
    is_complete: bool
    source: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SkillListResponse(APIModel):
    items: list[SkillResponse]
    total: int
    page: int
    page_size: int


class SkillImportResponse(APIModel):
    skill: SkillResponse
    reference_docs: list[SkillReferenceDocResponse]
    is_recognized: bool
