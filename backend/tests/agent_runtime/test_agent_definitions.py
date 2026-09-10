import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel


def test_default_agent_definitions_include_scene_draft_workflow_agent():
    from app.agent_runtime.agents.definitions import (
        DEFAULT_AGENT_KEYS,
        get_default_agent_definition,
    )

    assert DEFAULT_AGENT_KEYS == (
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
    build = get_default_agent_definition("build")
    assert build.kind == "primary"
    assert build.prompt_agent_name == "build"
    assert build.delegatable_agents == (
        "explore",
        "composer",
        "auditor",
        "writer",
        "actor",
        "reviewer",
    )

    plan = get_default_agent_definition("plan")
    assert plan.kind == "primary"
    assert plan.prompt_agent_name == "plan"
    assert plan.delegatable_agents == (
        "explore",
        "composer",
        "auditor",
        "writer",
        "actor",
        "reviewer",
    )

    discuss = get_default_agent_definition("discuss")
    assert discuss.display_name == "Discuss"
    assert discuss.description == ("围绕当前项目讨论设定与剧情，按所选范围读取资料，并保持信息边界")
    assert discuss.kind == "primary"
    assert discuss.prompt_agent_name == "discuss"
    assert discuss.model_id is None
    assert discuss.enabled_tool_categories == (
        "interaction",
        "project_change_proposal",
        "plan",
        "chapter_read",
        "summary_read",
        "world_read",
        "note_read",
        "character_read",
    )
    assert discuss.color == "purple"
    assert discuss.icon == "lightbulb"
    assert discuss.delegatable_agents == ()
    assert not any(category.endswith("_write") for category in discuss.enabled_tool_categories)

    draft = get_default_agent_definition("draft")
    assert draft.kind == "primary"
    assert draft.prompt_agent_name == "draft"
    assert draft.metadata["workflow_only"] is True
    assert draft.metadata["supports_global_context"] is True
    assert not any(category.endswith("_write") for category in draft.enabled_tool_categories)

    for key in DEFAULT_AGENT_KEYS[2:]:
        definition = get_default_agent_definition(key)
        assert definition.key == key
        assert definition.prompt_agent_name == key
        assert definition.enabled is True
        assert definition.source == "builtin"
        assert definition.delegatable_agents == ()


@pytest.mark.asyncio
async def test_load_agent_definition_prefers_db_record():
    from app.agent_runtime.agents.definitions import load_agent_definition
    from app.agent_runtime.persistence.model import AgentDefinitionRecord

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    try:
        async with factory() as session:
            session.add(
                AgentDefinitionRecord(
                    key="reviewer",
                    display_name="Custom Reviewer",
                    kind="subagent",
                    prompt_agent_name="reviewer",
                    model_id="model-reviewer",
                    enabled_tool_categories=["finish"],
                    enabled_skills=["skill-review"],
                    metadata_json={"scope": "custom"},
                    enabled=False,
                    order_index=10,
                )
            )
            await session.commit()

            definition = await load_agent_definition(session, "reviewer")

        assert definition.display_name == "Custom Reviewer"
        assert definition.model_id == "model-reviewer"
        assert definition.enabled_tool_categories == ("finish",)
        assert definition.enabled_skills == ("skill-review",)
        assert definition.metadata == {"scope": "custom"}
        assert definition.enabled is False
        assert definition.source == "builtin"
        assert definition.delegatable_agents == ()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_load_custom_agent_definition_has_source_custom():
    from app.agent_runtime.agents.definitions import load_agent_definition
    from app.agent_runtime.persistence.model import AgentDefinitionRecord

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    try:
        async with factory() as session:
            session.add(
                AgentDefinitionRecord(
                    key="custom-bot",
                    display_name="Custom Bot",
                    kind="subagent",
                    prompt_agent_name="custom-bot",
                    model_id=None,
                    enabled_tool_categories=["chapter_read"],
                    enabled_skills=["skill-custom"],
                    metadata_json={},
                    enabled=True,
                    source="custom",
                    delegatable_agents=["explore"],
                )
            )
            await session.commit()

            definition = await load_agent_definition(session, "custom-bot")

        assert definition.source == "custom"
        assert definition.enabled_skills == ("skill-custom",)
        assert definition.delegatable_agents == ("explore",)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_load_agent_definition_falls_back_to_default_when_db_row_missing():
    from app.agent_runtime.agents.definitions import (
        get_default_agent_definition,
        load_agent_definition,
    )

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    try:
        async with factory() as session:
            definition = await load_agent_definition(session, "explore")

        assert definition == get_default_agent_definition("explore")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_load_all_agent_definitions_merges_defaults_and_db_overrides():
    from app.agent_runtime.agents.definitions import load_all_agent_definitions
    from app.agent_runtime.persistence.model import AgentDefinitionRecord

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    try:
        async with factory() as session:
            session.add(
                AgentDefinitionRecord(
                    key="explore",
                    display_name="Custom Explore",
                    kind="subagent",
                    prompt_agent_name="explore",
                    model_id=None,
                    enabled_tool_categories=["chapter_read"],
                    enabled_skills=[],
                    metadata_json={},
                    enabled=False,
                    order_index=1,
                )
            )
            session.add(
                AgentDefinitionRecord(
                    key="custom-bot",
                    display_name="Custom Bot",
                    kind="subagent",
                    prompt_agent_name="custom-bot",
                    model_id=None,
                    enabled_tool_categories=["chapter_read"],
                    enabled_skills=[],
                    metadata_json={},
                    enabled=True,
                    source="custom",
                    order_index=99,
                )
            )
            await session.commit()

            definitions = await load_all_agent_definitions(session)

        assert "build" in definitions
        assert "plan" in definitions
        assert definitions["explore"].display_name == "Custom Explore"
        assert definitions["explore"].enabled is False
        assert definitions["custom-bot"].source == "custom"
    finally:
        await engine.dispose()


@pytest.mark.parametrize("field", ["supports_global_context", "workflow_only"])
@pytest.mark.parametrize("value", ["false", "true", 0, 1, None])
def test_capabilities_reject_non_boolean_values(field, value):
    from dataclasses import replace

    from pydantic import ValidationError

    from app.agent_runtime.agents.definitions import get_default_agent_definition

    with pytest.raises(ValidationError):
        replace(get_default_agent_definition("draft"), metadata={field: value})


def test_capabilities_snapshot_metadata_and_preserve_custom_fields():
    from dataclasses import replace

    from app.agent_runtime.agents.definitions import (
        get_default_agent_definition,
        supports_global_context,
    )

    metadata = {"supports_global_context": False, "display_hint": "custom"}
    definition = replace(get_default_agent_definition("draft"), metadata=metadata)
    metadata["supports_global_context"] = True
    assert supports_global_context(definition) is False
    assert definition.metadata["supports_global_context"] is False
    assert definition.metadata["display_hint"] == "custom"
    with pytest.raises(TypeError):
        definition.metadata["supports_global_context"] = True


@pytest.mark.parametrize("field,value", [("kind", "unknown"), ("source", "unknown")])
def test_database_definition_validates_closed_domains(field, value):
    from pydantic import ValidationError

    from app.agent_runtime.agents.definitions import agent_definition_from_record
    from app.agent_runtime.persistence.model import AgentDefinitionRecord

    record = AgentDefinitionRecord(
        key="custom",
        display_name="Custom",
        kind="primary",
        prompt_agent_name="custom",
        source="custom",
    )
    setattr(record, field, value)
    with pytest.raises(ValidationError):
        agent_definition_from_record(record)
