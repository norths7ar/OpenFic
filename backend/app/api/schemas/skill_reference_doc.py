"""SkillReferenceDoc API Schemas。"""

from datetime import datetime

from pydantic import ConfigDict, Field

from app.api.schemas.base import APIModel


class SkillReferenceDocCreate(APIModel):
    title: str = Field(default="", max_length=200, description="参考文档标题")
    content: str = Field(default="", description="参考文档内容")


class SkillReferenceDocUpdate(APIModel):
    title: str | None = Field(default=None, max_length=200, description="参考文档标题")
    content: str | None = Field(default=None, description="参考文档内容")


class SkillReferenceDocResponse(APIModel):
    id: str
    title: str
    content: str
    tokens: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
