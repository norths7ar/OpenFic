from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import ValidationError

from app.agent_runtime.agents.definitions import (
    get_default_agent_definition,
    supports_global_context,
)
from app.agent_runtime.context.knowledge_visibility import get_knowledge_scope
from app.agent_runtime.graph.orchestrator.graph import build_orchestrator_graph, primary_node
from app.agent_runtime.graph.orchestrator.state import OrchestratorState
from app.agent_runtime.runner.session_runner import SessionRunner
from app.api.routers import agent_runtime
from app.api.schemas.agent import AgentKnowledgeScopeRequest
from app.core.knowledge_scope import KnowledgeScope, merge_known_scope, validate_scope_change


def test_scope_wire_values_and_validation_are_unchanged():
    body = AgentKnowledgeScopeRequest.model_validate({"context_mode": "global"})
    assert body.context_mode is KnowledgeScope.GLOBAL
    assert body.model_dump(mode="json")["context_mode"] == "global"
    assert get_knowledge_scope({}) is KnowledgeScope.LOCAL
    with pytest.raises(ValidationError):
        AgentKnowledgeScopeRequest.model_validate({"context_mode": "all"})
    with pytest.raises(ValueError):
        get_knowledge_scope({"context_mode": "all"})
    with pytest.raises(ValueError):
        SessionRunner(
            session_id="invalid",
            task_id="task",
            model_config={"max_context_tokens": 1000},
            context_mode="all",
        )


def test_persisted_floor_and_role_policy_share_the_same_scope_values():
    restored = merge_known_scope(KnowledgeScope.GLOBAL, KnowledgeScope.LOCAL)
    assert restored is KnowledgeScope.GLOBAL
    with pytest.raises(ValueError, match="不能切回"):
        validate_scope_change(restored, KnowledgeScope.LOCAL, supports_global=True)
    with pytest.raises(ValueError, match="此 Agent"):
        validate_scope_change(restored, restored, supports_global=False)


@pytest.fixture
def scope_session(monkeypatch):
    task = SimpleNamespace(context_mode="local", is_running=False)
    graph = SimpleNamespace(
        aget_state=AsyncMock(return_value=SimpleNamespace(next=(), values={})),
        aupdate_state=AsyncMock(),
    )
    runner = SimpleNamespace(
        task_id="task",
        agent_key="plan",
        context_mode="local",
        _get_graph=AsyncMock(return_value=graph),
        peek_next_pending_user_message=MagicMock(return_value=None),
    )
    registry = SimpleNamespace(is_running=AsyncMock(return_value=False))
    session = MagicMock(commit=AsyncMock())
    monkeypatch.setattr(agent_runtime, "_get_runner", AsyncMock(return_value=runner))
    monkeypatch.setattr(agent_runtime, "get_agent_run_registry", lambda: registry)
    monkeypatch.setattr(agent_runtime.task_service, "get_task", AsyncMock(return_value=task))
    monkeypatch.setattr(agent_runtime, "list_active_child_runs", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        agent_runtime,
        "_validate_primary_agent",
        AsyncMock(side_effect=lambda _, key: get_default_agent_definition(key)),
    )
    return session, task, runner, graph, registry


@pytest.mark.asyncio
async def test_scope_upgrade_persists_and_cannot_be_reversed(scope_session):
    session, task, runner, graph, _ = scope_session
    body = AgentKnowledgeScopeRequest(context_mode="global")
    response = await agent_runtime.update_agent_knowledge_scope("scope", body, session)
    assert response.context_mode == task.context_mode == runner.context_mode == "global"
    session.commit.assert_awaited_once()
    assert graph.aupdate_state.call_args.args[1] == {"context_mode": "global", "agent_key": "plan"}
    with pytest.raises(HTTPException, match="不能切回"):
        await agent_runtime.update_agent_knowledge_scope(
            "scope",
            AgentKnowledgeScopeRequest(context_mode="local"),
            session,
        )


@pytest.mark.asyncio
async def test_real_materialized_empty_seed_can_upgrade(scope_session, monkeypatch):
    session, task, _, _, _ = scope_session
    runner = SessionRunner(
        session_id="empty-seed",
        task_id="task",
        project_id="project",
        agent_key="plan",
        model_config={"max_context_tokens": 1000},
    )
    graph = build_orchestrator_graph(InMemorySaver())
    runner._graph = graph
    await runner.materialize_state(
        agent_runtime._build_seed_state(
            session_id=runner.session_id,
            task_id=runner.task_id,
            project_id=runner.project_id,
            model_config=runner.model_config,
            agent_key="plan",
        )
    )
    snapshot = await graph.aget_state({"configurable": {"thread_id": runner.session_id}})
    assert snapshot.next == ("primary",)
    assert snapshot.values["is_completed"] is False
    monkeypatch.setattr(agent_runtime, "_get_runner", AsyncMock(return_value=runner))
    response = await agent_runtime.update_agent_knowledge_scope(
        runner.session_id,
        AgentKnowledgeScopeRequest(context_mode="global"),
        session,
    )
    assert response.context_mode == task.context_mode == runner.context_mode == "global"
    restored = await graph.aget_state({"configurable": {"thread_id": runner.session_id}})
    assert restored.values["context_mode"] == "global"


@pytest.mark.asyncio
async def test_real_interrupted_graph_cannot_upgrade(scope_session, monkeypatch):
    session, _, _, _, _ = scope_session
    runner = SessionRunner(
        session_id="interrupted-scope",
        task_id="task",
        project_id="project",
        agent_key="plan",
        model_config={"max_context_tokens": 1000},
    )

    def ask_user(_state):
        interrupt({"question": "continue?"})
        return {"is_completed": True}

    builder = StateGraph(OrchestratorState)
    builder.add_node("primary", ask_user)
    builder.add_edge(START, "primary")
    builder.add_edge("primary", END)
    graph = builder.compile(checkpointer=InMemorySaver())
    runner._graph = graph
    seed = agent_runtime._build_seed_state(
        session_id=runner.session_id,
        task_id=runner.task_id,
        project_id=runner.project_id,
        model_config=runner.model_config,
        agent_key="plan",
    )
    await runner.materialize_state(seed)
    await graph.ainvoke(
        {**seed, "user_request": "plan", "current_revision_id": "revision"},
        {"configurable": {"thread_id": runner.session_id}},
    )
    snapshot = await graph.aget_state({"configurable": {"thread_id": runner.session_id}})
    assert snapshot.next == ("primary",)
    assert snapshot.interrupts
    monkeypatch.setattr(agent_runtime, "_get_runner", AsyncMock(return_value=runner))
    with pytest.raises(HTTPException) as error:
        await agent_runtime.update_agent_knowledge_scope(
            runner.session_id,
            AgentKnowledgeScopeRequest(context_mode="global"),
            session,
        )
    assert error.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("active", ["registry", "task", "checkpoint", "pending", "child"])
async def test_scope_upgrade_requires_finished_turn(scope_session, monkeypatch, active):
    session, task, runner, graph, registry = scope_session
    if active == "registry":
        registry.is_running.return_value = True
    elif active == "task":
        task.is_running = True
    elif active == "checkpoint":
        graph.aget_state.return_value.next = ("primary",)
    elif active == "pending":
        runner.peek_next_pending_user_message.return_value = ("message", "queued")
    else:
        monkeypatch.setattr(
            agent_runtime,
            "list_active_child_runs",
            AsyncMock(
                return_value=[SimpleNamespace(status="waiting_user")],
            ),
        )
    with pytest.raises(HTTPException) as error:
        await agent_runtime.update_agent_knowledge_scope(
            "scope",
            AgentKnowledgeScopeRequest(context_mode="global"),
            session,
        )
    assert error.value.status_code == 409
    assert task.context_mode == runner.context_mode == "local"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_global_scope_rejects_build_role(scope_session):
    session, task, runner, _, _ = scope_session
    task.context_mode = runner.context_mode = "global"
    with pytest.raises(HTTPException) as error:
        await agent_runtime.update_agent_knowledge_scope(
            "scope",
            AgentKnowledgeScopeRequest(context_mode="global", agent_key="build"),
            session,
        )
    assert error.value.status_code == 400
    assert runner.agent_key == "plan"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "checkpoint_scope,runtime_scope", [("global", "local"), ("local", "global")]
)
async def test_checkpoint_or_runtime_global_cannot_execute_build(checkpoint_scope, runtime_scope):
    with pytest.raises(ValueError, match="全局资料"):
        await primary_node(
            {"agent_key": "build", "context_mode": checkpoint_scope},
            {"configurable": {"context_mode": runtime_scope}},
        )


def test_primary_role_scope_boundaries():
    assert supports_global_context(get_default_agent_definition("plan"))
    assert supports_global_context(get_default_agent_definition("discuss"))
    assert not supports_global_context(get_default_agent_definition("build"))


@pytest.mark.asyncio
@pytest.mark.parametrize("task_scope,checkpoint_scope", [("global", "local"), ("local", "global")])
async def test_restored_scope_never_downgrades_or_restores_build(
    monkeypatch, task_scope, checkpoint_scope
):
    task = SimpleNamespace(id="restore-task", project_id="project", context_mode=task_scope)
    graph = SimpleNamespace(
        aget_state=AsyncMock(
            return_value=SimpleNamespace(
                values={
                    "agent_key": "build",
                    "context_mode": checkpoint_scope,
                    "model_config": {"max_context_tokens": 1000},
                }
            )
        ),
        aupdate_state=AsyncMock(),
    )
    monkeypatch.setattr(agent_runtime.SessionRunner, "_get_graph", AsyncMock(return_value=graph))
    monkeypatch.setattr(
        agent_runtime.task_service, "get_task_by_agent_session_id", AsyncMock(return_value=task)
    )
    monkeypatch.setattr(
        agent_runtime,
        "_validate_primary_agent",
        AsyncMock(
            side_effect=lambda _, key: get_default_agent_definition(key),
        ),
    )
    session = MagicMock(commit=AsyncMock())
    agent_runtime._SESSION_RUNNERS.pop("scope-restore", None)
    try:
        runner = await agent_runtime._get_runner(
            "scope-restore", session, {"max_context_tokens": 1000}
        )
        assert runner.context_mode == task.context_mode == "global"
        assert runner.agent_key == "discuss"
        assert any(
            call.args[1].get("agent_key") == "discuss"
            for call in graph.aupdate_state.call_args_list
        )
    finally:
        agent_runtime._SESSION_RUNNERS.pop("scope-restore", None)
