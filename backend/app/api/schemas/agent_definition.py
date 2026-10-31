"""Agent Definition API Schemas。"""

from typing import Any

from pydantic import ConfigDict, Field, field_validator

from app.agent_runtime.agents.definitions import AgentCapabilities, AgentKind, AgentSource
from app.api.schemas.base import APIModel


class _AgentMetadataRequest(APIModel):
    @field_validator("metadata", check_fields=False)
    @classmethod
    def validate_capabilities(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None:
            AgentCapabilities.model_validate(value)
        return value


class AgentDefinitionResponse(APIModel):
    key: str
    display_name: str
    description: str = ""
    kind: AgentKind
    prompt_agent_name: str
    model_id: str | None = None
    enabled_tool_categories: list[str] = Field(default_factory=list)
    enabled_skills: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    source: AgentSource = "builtin"
    color: str | None = None
    icon: str | None = None
    delegatable_agents: list[str] = Field(default_factory=list)


class AgentDefinitionCreateRequest(_AgentMetadataRequest):
    key: str = Field(..., max_length=50)
    display_name: str = Field(..., max_length=200)
    description: str = Field(default="", max_length=1000)
    kind: AgentKind
    prompt_agent_name: str = Field(..., max_length=50)
    model_id: str | None = Field(default=None, max_length=100)
    enabled_tool_categories: list[str] = Field(default_factory=list)
    enabled_skills: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    color: str | None = Field(default=None, max_length=20)
    icon: str | None = Field(default=None, max_length=30)
    delegatable_agents: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class AgentDefinitionUpdateRequest(_AgentMetadataRequest):
    display_name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    kind: AgentKind | None = None
    prompt_agent_name: str | None = Field(default=None, max_length=50)
    model_id: str | None = Field(default=None, max_length=100)
    enabled_tool_categories: list[str] | None = None
    enabled_skills: list[str] | None = None
    metadata: dict[str, Any] | None = None
    enabled: bool | None = None
    color: str | None = Field(default=None, max_length=20)
    icon: str | None = Field(default=None, max_length=30)
    delegatable_agents: list[str] | None = None

    model_config = ConfigDict(extra="forbid")


class AgentDefinitionListResponse(APIModel):
    definitions: list[AgentDefinitionResponse]


class AgentToolCategoryResponse(APIModel):
    key: str
    name: str
    tool_keys: list[str] = Field(default_factory=list)


class AgentToolCategoryListResponse(APIModel):
    categories: list[AgentToolCategoryResponse]
