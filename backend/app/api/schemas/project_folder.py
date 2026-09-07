"""API schemas for shared single-level project folders."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ProjectFolderScope = Literal["writing", "discussion", "world", "character", "outline", "note"]


class ProjectFolderCreate(BaseModel):
    model_config = {"extra": "forbid"}
    scope: ProjectFolderScope
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None


class ProjectFolderUpdate(BaseModel):
    model_config = {"extra": "forbid"}
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


class ProjectFolderReorder(BaseModel):
    scope: ProjectFolderScope
    ordered_ids: list[str]


class ProjectFolderItemMove(BaseModel):
    scope: ProjectFolderScope
    item_id: str
    folder_id: str | None = None


class ProjectFolderResponse(BaseModel):
    id: str
    project_id: str
    scope: ProjectFolderScope
    title: str
    description: str | None = None
    order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectFolderListResponse(BaseModel):
    items: list[ProjectFolderResponse]
