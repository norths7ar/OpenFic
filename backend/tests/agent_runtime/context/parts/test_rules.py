from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.agent_runtime.context.parts.rules import build_rules
from app.storage.models.agent_rule import AgentRule


@pytest.mark.asyncio
async def test_rules_returns_none_when_empty(mock_session):
    with patch(
        "app.agent_runtime.context.parts.rules.agent_rule_service.list_all_rules",
        AsyncMock(return_value=[]),
    ):
        assert await build_rules(mock_session) is None


@pytest.mark.asyncio
async def test_rules_returns_none_when_empty_for_project(mock_session):
    with patch(
        "app.agent_runtime.context.parts.rules.agent_rule_service.list_all_rules",
        AsyncMock(return_value=[]),
    ) as mock_list:
        assert await build_rules(mock_session, project_id="proj-1") is None
    mock_list.assert_awaited_once_with(mock_session, "proj-1")


@pytest.mark.asyncio
async def test_rules_renders_pseudo_xml(mock_session):
    rules = [
        SimpleNamespace(content="不要透露身份"),
        SimpleNamespace(content="保持中文"),
    ]
    with patch(
        "app.agent_runtime.context.parts.rules.agent_rule_service.list_all_rules",
        AsyncMock(return_value=rules),
    ):
        msg = await build_rules(mock_session)
    assert msg is not None
    assert msg.role == "system"
    assert msg.metadata == {"part": "rules"}
    assert msg.content.startswith("<rules>")
    assert msg.content.endswith("</rules>")
    assert "- 不要透露身份" in msg.content
    assert "- 保持中文" in msg.content


@pytest.mark.asyncio
async def test_rules_include_global_and_current_project_only():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    try:
        async with factory() as session:
            session.add_all(
                [
                    AgentRule(content="全局规则", scope="global", order_index=1),
                    AgentRule(
                        content="当前项目规则",
                        scope="project",
                        project_id="proj-1",
                        order_index=2,
                    ),
                    AgentRule(
                        content="其他项目规则",
                        scope="project",
                        project_id="proj-2",
                        order_index=2,
                    ),
                ]
            )
            await session.commit()

            message = await build_rules(session, project_id="proj-1")

        assert message is not None
        assert "全局规则" in message.content
        assert "当前项目规则" in message.content
        assert "其他项目规则" not in message.content
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_rules_db_error_raises_context_build_error(mock_session):
    from app.agent_runtime.context.errors import ContextBuildError

    with patch(
        "app.agent_runtime.context.parts.rules.agent_rule_service.list_all_rules",
        AsyncMock(side_effect=RuntimeError("db down")),
    ):
        with pytest.raises(ContextBuildError) as exc_info:
            await build_rules(mock_session)
    assert exc_info.value.part == "rules"
