from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent_runtime.context import build_context
from app.agent_runtime.context.types import ContextMessage
from app.agent_runtime.graph.state import AgentRuntimeState


@pytest.fixture
def base_state() -> AgentRuntimeState:
    return cast(
        AgentRuntimeState,
        {
            "session_id": "s1",
            "task_id": "t1",
            "project_id": "p1",
            "model_config": {"max_context_tokens": 8000},
            "active_agent": "writer",
            "is_completed": False,
            "error": None,
            "retry_count": 0,
            "user_request": "写一段",
            "installed_skill_ids": [],
            "current_revision_id": None,
        },
    )


@pytest.fixture(autouse=True)
def _compress_setting_disabled() -> None:
    with (
        patch(
            "app.agent_runtime.context.processors.compress.setting_repo.get_by_key",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.agent_runtime.context.parts.session_plan.plan_service.get_plan_todos",
            new=AsyncMock(return_value=None),
        ),
    ):
        yield


@pytest.mark.asyncio
async def test_assembles_messages_in_order(base_state: AgentRuntimeState) -> None:
    sys_msgs = [
        ContextMessage(role="system", content="sys", metadata={"part": "system_prompt"}),
        ContextMessage(role="user", content="prompt-user", metadata={"part": "system_prompt"}),
        ContextMessage(
            role="assistant", content="prompt-assistant", metadata={"part": "system_prompt"}
        ),
    ]

    db_session = AsyncMock()
    build_rules_mock = AsyncMock(return_value=None)
    with (
        patch(
            "app.agent_runtime.context.build_context.build_system_prompt",
            new=AsyncMock(return_value=sys_msgs),
        ),
        patch(
            "app.agent_runtime.context.build_context.build_rules",
            new=build_rules_mock,
        ),
        patch(
            "app.agent_runtime.context.build_context.build_skills",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.agent_runtime.context.build_context.compaction_repo.list_by_session",
            new=AsyncMock(return_value=[]),
        ),
    ):
        out = await build_context(
            state=base_state,
            agent_name="writer",
            node_messages=[{"role": "user", "content": "hi", "metadata": {"part": "history"}}],
            db_session=db_session,
        )

    assert isinstance(out[0], SystemMessage)
    assert out[0].content == "sys"
    assert isinstance(out[1], HumanMessage)
    assert out[1].content == "prompt-user"
    assert out[2].type == "ai"
    assert out[2].content == "prompt-assistant"
    assert isinstance(out[-1], HumanMessage)
    assert out[-1].content == "hi"
    build_rules_mock.assert_awaited_once_with(db_session, "p1")
