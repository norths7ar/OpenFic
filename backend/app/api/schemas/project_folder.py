"""API schemas for shared single-level project folders."""

from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field

from app.api.schemas.base import APIModel

ProjectFolderScope = Literal["writing", "discussion", "world", "character", "outline", "note"]


class ProjectFolderCreate(APIModel):
    model_config = ConfigDict(extra="forbid")
    scope: ProjectFolderScope
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None


class ProjectFolderUpdate(APIModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


class ProjectFolderReorder(APIModel):
    scope: ProjectFolderScope
    ordered_ids: list[str]


class ProjectFolderItemMove(APIModel):
    scope: ProjectFolderScope
    item_id: str
    folder_id: str | None = None


class ProjectFolderResponse(APIModel):
    id: str
    project_id: str
    scope: ProjectFolderScope
    title: str
    description: str | None = None
    order: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectFolderListResponse(APIModel):
    items: list[ProjectFolderResponse]
