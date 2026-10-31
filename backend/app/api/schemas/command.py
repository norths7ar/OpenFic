from typing import Literal

from pydantic import Field

from app.api.schemas.base import APIModel


class CommandCandidateItem(APIModel):
    kind: Literal["skill"] = Field(description="命令类型")
    id: str = Field(description="命令关联对象 ID")
    name: str = Field(description="命令名称")
    description: str = Field(description="命令说明")


class CommandSearchResponse(APIModel):
    items: list[CommandCandidateItem] = Field(description="命令候选项")
