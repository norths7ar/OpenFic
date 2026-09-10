"""Default primary and subagent definitions."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, StrictBool, TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.agent_runtime.persistence.model import AgentDefinitionRecord

AgentKind = Literal["primary", "subagent"]
AgentSource = Literal["builtin", "custom"]
_AGENT_KIND = TypeAdapter(AgentKind)
_AGENT_SOURCE = TypeAdapter(AgentSource)


class AgentCapabilities(BaseModel):
    """Validated behavior fields; unrelated presentation metadata stays extensible."""

    model_config = ConfigDict(frozen=True)

    supports_global_context: StrictBool = False
    workflow_only: StrictBool = False


@dataclass(frozen=True)
class AgentDefinition:
    key: str
    display_name: str
    description: str
    kind: AgentKind
    prompt_agent_name: str
    model_id: str | None
    enabled_tool_categories: tuple[str, ...]
    enabled_skills: tuple[str, ...]
    metadata: Mapping[str, Any]
    enabled: bool = True
    source: AgentSource = "builtin"
    color: str | None = None
    icon: str | None = None
    delegatable_agents: tuple[str, ...] = ()
    capabilities: AgentCapabilities = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _AGENT_KIND.validate_python(self.kind))
        object.__setattr__(self, "source", _AGENT_SOURCE.validate_python(self.source))
        metadata = dict(self.metadata)
        # Validate supplied capabilities before applying fixed built-in boundaries.
        capabilities = AgentCapabilities.model_validate(metadata)
        if self.key in {"build", "plan", "discuss"}:
            metadata["supports_global_context"] = self.key != "build"
            capabilities = AgentCapabilities.model_validate(metadata)
        object.__setattr__(self, "metadata", MappingProxyType(metadata))
        object.__setattr__(self, "capabilities", capabilities)


DEFAULT_AGENT_KEYS: tuple[str, ...] = (
    "build",
    "plan",
    "discuss",
    "draft",
    "explore",
    "composer",
    "auditor",
    "writer",
    "reviewer",
    "actor",
)


DEFAULT_AGENT_DEFINITIONS: Mapping[str, AgentDefinition] = MappingProxyType(
    {
        "build": AgentDefinition(
            key="build",
            display_name="Build",
            description="默认的 Agent，执行通用的写作任务，并在需要时调度子 Agent 完成工作",
            kind="primary",
            prompt_agent_name="build",
            model_id=None,
            enabled_tool_categories=(
                "orchestration",
                "interaction",
                "plan",
                "chapter_read",
                "chapter_write",
                "summary_read",
                "world_read",
                "world_write",
                "note_read",
                "note_write",
                "character_read",
                "character_write",
            ),
            enabled_skills=(),
            metadata=MappingProxyType({}),
            color="blue",
            icon="pen-tool",
            delegatable_agents=(
                "explore",
                "composer",
                "auditor",
                "writer",
                "actor",
                "reviewer",
            ),
        ),
        "plan": AgentDefinition(
            key="plan",
            display_name="Plan",
            description="专注于规划和协调，组织子 Agent 工作、审查与交付，负责执行系统写作的任务",
            kind="primary",
            prompt_agent_name="plan",
            model_id=None,
            enabled_tool_categories=(
                "orchestration",
                "interaction",
                "plan",
                "chapter_read",
                "summary_read",
                "world_read",
                "note_read",
                "character_read",
            ),
            enabled_skills=(),
            metadata=MappingProxyType({"supports_global_context": True}),
            color="green",
            icon="list-checks",
            delegatable_agents=(
                "explore",
                "composer",
                "auditor",
                "writer",
                "actor",
                "reviewer",
            ),
        ),
        "discuss": AgentDefinition(
            key="discuss",
            display_name="Discuss",
            description=("围绕当前项目讨论设定与剧情，按所选范围读取资料，并保持信息边界"),
            kind="primary",
            prompt_agent_name="discuss",
            model_id=None,
            enabled_tool_categories=(
                "interaction",
                "project_change_proposal",
                "plan",
                "chapter_read",
                "summary_read",
                "world_read",
                "note_read",
                "character_read",
            ),
            enabled_skills=(),
            metadata=MappingProxyType({"supports_global_context": True}),
            color="purple",
            icon="lightbulb",
            delegatable_agents=(),
        ),
        "draft": AgentDefinition(
            key="draft",
            display_name="Scene Draft",
            description="根据当前章节与所选资料生成可编辑的场景初稿，不直接修改正式正文",
            kind="primary",
            prompt_agent_name="draft",
            model_id=None,
            enabled_tool_categories=(
                "interaction",
                "chapter_read",
                "summary_read",
                "world_read",
                "note_read",
                "character_read",
            ),
            enabled_skills=(),
            metadata=MappingProxyType({"workflow_only": True, "supports_global_context": True}),
            color="amber",
            icon="file-pen-line",
            delegatable_agents=(),
        ),
        "explore": AgentDefinition(
            key="explore",
            display_name="Explore",
            description="负责信息搜集、上下文梳理与证据查找",
            kind="subagent",
            prompt_agent_name="explore",
            model_id=None,
            enabled_tool_categories=(
                "chapter_read",
                "summary_read",
                "world_read",
                "note_read",
                "character_read",
            ),
            enabled_skills=(),
            metadata=MappingProxyType({}),
        ),
        "composer": AgentDefinition(
            key="composer",
            display_name="Composer",
            description="负责剧情设计、结构规划与写作方案的组织",
            kind="subagent",
            prompt_agent_name="composer",
            model_id=None,
            enabled_tool_categories=(
                "chapter_read",
                "summary_read",
                "world_read",
                "world_write",
                "plan",
                "note_read",
                "note_write",
                "character_read",
                "character_write",
            ),
            enabled_skills=(),
            metadata=MappingProxyType({}),
        ),
        "auditor": AgentDefinition(
            key="auditor",
            display_name="Auditor",
            description="负责审查计划，产出评审意见、指出问题并提出修正建议。",
            kind="subagent",
            prompt_agent_name="auditor",
            model_id=None,
            enabled_tool_categories=(
                "chapter_read",
                "summary_read",
                "world_read",
                "plan",
                "note_read",
                "character_read",
            ),
            enabled_skills=(),
            metadata=MappingProxyType({}),
        ),
        "writer": AgentDefinition(
            key="writer",
            display_name="Writer",
            description="负责章节内容撰写、补写与正文修改。",
            kind="subagent",
            prompt_agent_name="writer",
            model_id=None,
            enabled_tool_categories=(
                "chapter_read",
                "summary_read",
                "world_read",
                "plan",
                "chapter_write",
                "note_read",
                "note_write",
                "character_read",
            ),
            enabled_skills=(),
            metadata=MappingProxyType({}),
        ),
        "actor": AgentDefinition(
            key="actor",
            display_name="Actor",
            description="负责按既定目标执行修改并推进具体动作。",
            kind="subagent",
            prompt_agent_name="actor",
            model_id=None,
            enabled_tool_categories=(
                "plan",
                "chapter_read",
                "chapter_write",
                "summary_read",
                "world_read",
                "world_write",
                "note_read",
                "note_write",
                "character_read",
                "character_write",
            ),
            enabled_skills=(),
            metadata=MappingProxyType({}),
        ),
        "reviewer": AgentDefinition(
            key="reviewer",
            display_name="Reviewer",
            description="负责审查写作内容，产出评审意见、指出问题并提出修正建议。",
            kind="subagent",
            prompt_agent_name="reviewer",
            model_id=None,
            enabled_tool_categories=(
                "chapter_read",
                "summary_read",
                "world_read",
                "plan",
                "character_read",
                "note_read",
            ),
            enabled_skills=(),
            metadata=MappingProxyType({}),
        ),
    }
)


def get_default_agent_definition(key: str) -> AgentDefinition:
    return DEFAULT_AGENT_DEFINITIONS[key]


def supports_global_context(definition: AgentDefinition) -> bool:
    return definition.capabilities.supports_global_context


def agent_definition_from_record(record: AgentDefinitionRecord) -> AgentDefinition:
    return AgentDefinition(
        key=record.key,
        display_name=record.display_name,
        description=record.description,
        kind=_AGENT_KIND.validate_python(record.kind),
        prompt_agent_name=record.prompt_agent_name,
        model_id=record.model_id,
        enabled_tool_categories=tuple(record.enabled_tool_categories or ()),
        enabled_skills=tuple(record.enabled_skills or ()),
        metadata=record.metadata_json,
        enabled=record.enabled,
        source=_AGENT_SOURCE.validate_python(record.source),
        color=record.color,
        icon=record.icon,
        delegatable_agents=tuple(record.delegatable_agents or ()),
    )


async def load_agent_definition(
    session: AsyncSession,
    key: str,
) -> AgentDefinition:
    result = await session.execute(
        select(AgentDefinitionRecord).where(col(AgentDefinitionRecord.key) == key)
    )
    record = result.scalar_one_or_none()
    if record is not None:
        return agent_definition_from_record(record)
    return get_default_agent_definition(key)


async def load_all_agent_definitions(
    session: AsyncSession,
) -> dict[str, AgentDefinition]:
    definitions = {key: DEFAULT_AGENT_DEFINITIONS[key] for key in DEFAULT_AGENT_KEYS}
    result = await session.execute(
        select(AgentDefinitionRecord).order_by(
            col(AgentDefinitionRecord.order_index),
            col(AgentDefinitionRecord.key),
        )
    )
    for record in result.scalars():
        definitions[record.key] = agent_definition_from_record(record)
    return definitions
