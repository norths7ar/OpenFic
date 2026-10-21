"""章节正文修改后，最终模型上下文不得继续使用旧摘要。"""

from pathlib import Path

import pytest
import pytest_asyncio
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.agent_runtime.graph.react_agent import create_react_agent
from app.agent_runtime.tools.impls.chapter.read_chapter import ReadChapterTool
from app.agent_runtime.tools.impls.context.read_chapter_summaries import ReadChapterSummariesTool
from app.agent_runtime.types import ReactAgentConfig, TerminationCondition
from app.memory.chapter.summary_service import (
    is_chapter_summary_stale,
    save_chapter_summary_result,
)
from app.storage import database
from app.storage.repos import volume_repo
from app.storage.services import chapter_service, project_service
from tests.model_registry import register_sqlmodel_models


@pytest_asyncio.fixture
async def summary_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    register_sqlmodel_models()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'summaries.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    # 工具自行创建会话；将连接入口指向同一个真实隔离数据库。
    monkeypatch.setattr(database, "_engine", engine)
    monkeypatch.setattr(database, "_async_session_factory", factory)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _capture_model_context(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    *,
    project_id: str,
    volume_id: str,
    chapter_order: int,
) -> list[BaseMessage]:
    request = "请结合章节摘要与当前正文继续创作，保留当前情节。"
    state = {
        "session_id": "summary-freshness",
        "task_id": "summary-freshness-task",
        "project_id": project_id,
        "model_config": {"max_context_tokens": 100_000},
        "user_request": request,
        "current_revision_id": None,
    }
    captured: list[list[BaseMessage]] = []

    async def invoke_model(_model, messages, **_kwargs):
        captured.append(list(messages))
        if len(captured) == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "read-summary",
                        "name": "read_chapter_summaries",
                        "args": {"orders": [chapter_order]},
                    },
                    {
                        "id": "read-current-body",
                        "name": "read_chapter",
                        "args": {
                            "volume_ref": {"type": "id", "value": volume_id},
                            "chapter_ref": {"type": "order", "value": chapter_order},
                        },
                    },
                ],
            )
        assert len(captured) == 2, "读取摘要和正文后不应再次调用工具"
        return AIMessage(content="已读取创作上下文。")

    monkeypatch.setattr("app.agent_runtime.graph.react_agent._invoke_model", invoke_model)
    graph = create_react_agent(
        ReactAgentConfig(
            name="draft",
            tools=[ReadChapterSummariesTool(_state=state), ReadChapterTool(_state=state)],
            termination=TerminationCondition(mode="no_tool_call"),
        )
    )
    await graph.ainvoke(
        {"messages": [HumanMessage(content=request)], "iteration_count": 0},
        config={"configurable": {"runtime_state": state, "db_session": session}},
    )
    assert len(captured) == 2, "必须捕获工具结果组装后的最终模型输入"
    final_messages = captured[-1]
    assert any(isinstance(m, HumanMessage) and m.content == request for m in final_messages)
    assert {m.tool_call_id for m in final_messages if isinstance(m, ToolMessage)} == {
        "read-summary",
        "read-current-body",
    }
    return final_messages


@pytest.mark.asyncio
async def test_body_update_excludes_old_summary_from_final_model_context(
    summary_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """保护结果：正文更新后，续写模型不再收到旧摘要，同时仍收到当前正文和用户请求。"""
    old_body = "林舟将密信交给北城守卫，约定明早随商队从北门出发。" * 30
    old_summary = "林舟已把密信交给北城守卫，决定明早随商队离城。"
    current_plot = "密信已被焚毁，林舟决定留在南城寻找失踪的妹妹。"
    current_body = current_plot + "他沿着河岸逐一询问渡船上的旅客，记录妹妹最后的行踪。" * 30

    async with summary_database() as session:
        project = await project_service.create_project(session, title="摘要时效验证")
        volume = (await volume_repo.list_by_project(session, project.id))[0]
        chapter = await chapter_service.create_chapter(
            session, project.id, volume.id, title="密信的去向", content=old_body
        )
        summary = await save_chapter_summary_result(
            session,
            chapter.id,
            start_time="清晨",
            end_time="傍晚",
            characters=["林舟", "守卫"],
            locations=["北城"],
            summary=old_summary,
            token_count=40,
            model_id=None,
            job_id=None,
        )
        await session.commit()
        assert not is_chapter_summary_stale(summary, chapter)

        context_args = {
            "project_id": project.id,
            "volume_id": volume.id,
            "chapter_order": chapter.order,
        }
        before = await _capture_model_context(session, monkeypatch, **context_args)
        assert old_summary in "\n".join(str(message.content) for message in before)

        chapter = await chapter_service.update_chapter(session, chapter.id, content=current_body)
        await session.commit()
        assert is_chapter_summary_stale(summary, chapter)

    # 新会话重新读取已提交的正文，排除 ORM 缓存造成的假象。
    async with summary_database() as session:
        after = await _capture_model_context(session, monkeypatch, **context_args)
    final_context = "\n".join(str(message.content) for message in after)
    assert current_body in final_context, "过滤旧摘要不能丢失当前正文"
    assert old_summary not in final_context, "正文已更新，旧摘要仍进入最终模型上下文"
