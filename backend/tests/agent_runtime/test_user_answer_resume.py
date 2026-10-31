"""真实编排图的用户提问、持久化等待与回答恢复主流程。"""

import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.types import Command
from pydantic import Field
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.agent_runtime.graph.orchestrator.graph import build_orchestrator_graph
from app.agent_runtime.runner import checkpointer
from app.storage import database
from app.storage.models.project import Project
from app.storage.models.task import Task
from tests.model_registry import register_sqlmodel_models

_QUESTION = "开场采用哪种方式？"
_REQUESTS = {
    "opening-a": "为山城故事拟定开场方案，先确认开场方式。",
    "opening-b": "为海港故事拟定开场方案，先确认开场方式。",
}


class _ClarifyingModel(BaseChatModel):
    """只替代外部模型；根据真实工具返回的答案生成最终方案。"""

    calls: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "gap-test-clarifying-model"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls.append(list(messages))
        request = next(message.content for message in messages if isinstance(message, HumanMessage))
        session_id = next(key for key, value in _REQUESTS.items() if value == request)
        answers = [message for message in messages if isinstance(message, ToolMessage)]
        if answers:
            answer = json.loads(answers[0].content)[0]["answer"]
            response = AIMessage(content=f"{request}开场方案：{answer}。")
        else:
            response = AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": f"choose-{session_id}",
                        "name": "ask_user",
                        "args": {
                            "questions": [
                                {
                                    "title": _QUESTION,
                                    "description": request,
                                    "options": [
                                        {"label": "追逐", "description": "从行动开始"},
                                        {"label": "对话", "description": "从人物交流开始"},
                                    ],
                                }
                            ]
                        },
                    }
                ],
            )
        return ChatResult(generations=[ChatGeneration(message=response)])


@pytest_asyncio.fixture
async def answer_runtime(monkeypatch):
    scratch = Path(__file__).resolve().parents[3] / ".tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    day = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d")
    with TemporaryDirectory(prefix=f"{day}-user-answer-resume-", dir=scratch) as directory:
        root = Path(directory)
        monkeypatch.setenv("AGENT_CHECKPOINT_DB", str(root / "checkpoints.db"))
        monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(root / "tiktoken"))
        monkeypatch.setattr(checkpointer, "_checkpointer", None)
        engine = create_async_engine(f"sqlite+aiosqlite:///{root / 'business.db'}")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(database, "_engine", engine)
        monkeypatch.setattr(database, "_async_session_factory", factory)
        register_sqlmodel_models()
        try:
            async with engine.begin() as connection:
                await connection.run_sync(SQLModel.metadata.create_all)
            async with factory() as session:
                session.add(Project(id="opening-project", title="开场方案"))
                await session.flush()
                session.add_all(
                    Task(
                        id=f"task-{session_id}",
                        project_id="opening-project",
                        title=request,
                        mode="agent",
                        agent_session_id=session_id,
                    )
                    for session_id, request in _REQUESTS.items()
                )
                await session.commit()
            yield factory
        finally:
            await checkpointer.close_checkpointer()
            await engine.dispose()


async def _drive(graph, graph_input, config):
    replies = []
    async for event in graph.astream_events(graph_input, config=config, version="v2"):
        if event["event"] == "on_chat_model_end":
            replies.append(event["data"]["output"].content)
    return replies


@pytest.mark.asyncio
async def test_user_answer_resumes_persisted_task_without_answering_another_task(
    answer_runtime, monkeypatch
):
    """保护结果：提问后原任务持久化等待，回答只进入对应调用并产出方案，不推进另一待回答任务。"""
    model = _ClarifyingModel()
    monkeypatch.setattr(
        "app.agent_runtime.graph.orchestrator.graph.create_chat_model", lambda _config: model
    )

    async def discard_socket_event(*args, **kwargs):
        pass

    monkeypatch.setattr("app.agent_runtime.graph.node_events.emit", discard_socket_event)
    model_config = {
        "provider_type": "openai",
        "model_id": "gap-test",
        "api_key": "unused",
        "base_url": "",
        "max_context_tokens": 128000,
    }
    graph = build_orchestrator_graph(checkpointer=await checkpointer.get_checkpointer())
    pending = {}
    for session_id, request in _REQUESTS.items():
        async with answer_runtime() as session:
            config = {
                "configurable": {
                    "thread_id": session_id,
                    "db_session": session,
                    "model_config": model_config,
                }
            }
            await _drive(
                graph,
                {
                    "session_id": session_id,
                    "task_id": f"task-{session_id}",
                    "project_id": "opening-project",
                    "model_config": model_config,
                    "agent_key": "build",
                    "messages": [],
                    "user_request": request,
                    "is_completed": False,
                },
                config,
            )
            state = await graph.aget_state(config)
            interrupts = [interrupt for task in state.tasks for interrupt in task.interrupts]
            assert len(interrupts) == 1
            assert interrupts[0].value["type"] == "ask_user"
            assert interrupts[0].value["questions"][0]["title"] == _QUESTION
            assert interrupts[0].value["questions"][0]["description"] == request
            assert state.next
            assert state.values["is_completed"] is False
            pending[session_id] = (interrupts[0], state.config)
    assert len(model.calls) == 2
    assert all(not any(isinstance(m, ToolMessage) for m in call) for call in model.calls)

    # 丢弃图实例与连接；新图必须从磁盘找回等待中的问题，而非依赖内存续跑。
    await checkpointer.close_checkpointer()
    del graph
    graph = build_orchestrator_graph(checkpointer=await checkpointer.get_checkpointer())
    for index, (session_id, answer) in enumerate(
        (("opening-a", "追逐"), ("opening-b", "对话")), start=1
    ):
        async with answer_runtime() as session:
            config = {
                "configurable": {
                    "thread_id": session_id,
                    "db_session": session,
                    "model_config": model_config,
                }
            }
            interrupt, checkpoint_config = pending[session_id]
            restored = await graph.aget_state(config)
            assert restored.config == checkpoint_config
            assert restored.next
            assert restored.values["task_id"] == f"task-{session_id}"
            assert restored.values["is_completed"] is False
            assert len(model.calls) == index + 1
            answers = [{"question": _QUESTION, "answer": answer}]
            replies = await _drive(
                graph,
                Command(
                    resume={
                        interrupt.id: {
                            "action_type": "clarification",
                            "action_id": interrupt.id,
                            "answer": answers,
                        }
                    }
                ),
                config,
            )
            assert replies == [f"{_REQUESTS[session_id]}开场方案：{answer}。"]
            assert len(model.calls) == index + 2
            delivered = [m for m in model.calls[-1] if isinstance(m, ToolMessage)]
            assert len(delivered) == 1
            assert delivered[0].tool_call_id == f"choose-{session_id}"
            matching_calls = [
                call
                for message in model.calls[-1]
                if isinstance(message, AIMessage)
                for call in message.tool_calls
                if call["id"] == delivered[0].tool_call_id
            ]
            assert len(matching_calls) == 1
            assert matching_calls[0]["name"] == "ask_user"
            assert matching_calls[0]["args"]["questions"][0]["description"] == _REQUESTS[session_id]
            assert json.loads(delivered[0].content) == answers
            completed = await graph.aget_state(config)
            assert completed.next == ()
            assert completed.values["is_completed"] is True
            assert completed.values["task_id"] == f"task-{session_id}"
            if session_id == "opening-a":
                other = await graph.aget_state({"configurable": {"thread_id": "opening-b"}})
                assert other.config == pending["opening-b"][1]
                assert other.next
                assert other.values["is_completed"] is False
