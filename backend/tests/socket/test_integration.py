import asyncio
import socket

import pytest
import pytest_asyncio
import socketio as socketio_lib  # type: ignore[import-untyped]
import uvicorn
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.agent_runtime.streaming.replay_buffer import get_agent_event_replay_buffer
from app.socket import background_project_room, emit, init_socketio
from app.socket.handlers import (
    get_connection_state,
)
from app.storage import database
from app.storage.models.chapter import Chapter
from app.storage.models.chapter_summary import ChapterSummary
from app.storage.models.project import Project
from app.storage.models.project_folder import ProjectFolder as Volume
from tests.model_registry import register_sqlmodel_models


@pytest_asyncio.fixture(loop_scope="function")
async def socket_db_factory():
    from sqlalchemy.pool import StaticPool

    register_sqlmodel_models()

    original_factory = database._async_session_factory
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    database._async_session_factory = factory
    try:
        yield factory
    finally:
        database._async_session_factory = original_factory
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="function")
async def server(socket_db_factory):
    """Start a real ASGI server for integration testing."""
    port_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    port_socket.bind(("127.0.0.1", 0))
    port = port_socket.getsockname()[1]
    port_socket.close()

    test_app = FastAPI()
    asgi_app = init_socketio(test_app)

    # Avoid Uvicorn's legacy websockets backend, which emits deprecation warnings
    # with the installed websockets package.
    config = uvicorn.Config(
        asgi_app,
        host="127.0.0.1",
        port=port,
        log_level="error",
        ws="websockets-sansio",
    )
    srv = uvicorn.Server(config)

    task = asyncio.create_task(srv.serve())
    # Wait for server to be ready
    while not srv.started:
        await asyncio.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    await task

    # Reset state after test
    get_connection_state().on_disconnect()


async def _seed_project(
    socket_db_factory,
    *,
    project_id: str,
    chapter_id: str,
    status: str | None = None,
) -> None:
    async with socket_db_factory() as session:
        project = Project(id=project_id, title=f"项目 {project_id}", description="")
        volume = Volume(
            scope="writing",
            id=f"{project_id}-volume-1",
            project_id=project_id,
            title="第一卷",
            order=1,
            item_count=1,
        )
        chapter = Chapter(
            id=chapter_id,
            project_id=project_id,
            volume_id=volume.id,
            title=f"章节 {chapter_id}",
            content="正文" * 400,
            word_count=800,
            order=1,
        )
        session.add(project)
        session.add(volume)
        session.add(chapter)
        if status is not None:
            session.add(
                ChapterSummary(
                    project_id=project_id,
                    summary_type="chapter",
                    status=status,
                    chapter_id=chapter_id,
                    chapter_order=1,
                    start_order=1,
                    end_order=1,
                )
            )
        await session.commit()


async def _expect_background_joined_and_snapshot(client, project_id: str):
    joined_event = await asyncio.wait_for(client.receive(), timeout=2.0)
    assert joined_event[0] == "background:joined"
    assert joined_event[1] == {"project_id": project_id}

    snapshot_event = await asyncio.wait_for(client.receive(), timeout=2.0)
    assert snapshot_event[0] == "background:snapshot"
    snapshot = snapshot_event[1]
    assert snapshot["project_id"] == project_id
    assert isinstance(snapshot["project_revision"], int)
    assert snapshot["project_revision"] > 0
    assert "summary" in snapshot
    assert "statuses" in snapshot["summary"]
    assert "maintenance" in snapshot["summary"]
    return snapshot


@pytest.fixture(autouse=True)
def reset_state():
    get_connection_state().on_disconnect()
    get_agent_event_replay_buffer().clear_all()
    yield
    get_connection_state().on_disconnect()
    get_agent_event_replay_buffer().clear_all()


class TestSocketIntegration:


    async def test_join_agent_session_room_receives_room_event(self, server):
        client = socketio_lib.AsyncSimpleClient()
        await client.connect(server, socketio_path="/socket.io")
        await asyncio.sleep(0.1)

        await client.emit("agent:join", {"session_id": "s1"})
        joined_event = await asyncio.wait_for(client.receive(), timeout=2.0)
        assert joined_event[0] == "agent:joined"
        assert joined_event[1] == {"session_id": "s1"}

        await emit("agent:token", {"session_id": "s1", "content": "hello"}, room="agent_session:s1")
        event = await asyncio.wait_for(client.receive(), timeout=2.0)
        assert event[0] == "agent:token"
        assert event[1] == {"session_id": "s1", "content": "hello"}

        await client.disconnect()








    async def test_background_project_rooms_and_snapshots_are_isolated(
        self, server, socket_db_factory
    ):
        await _seed_project(socket_db_factory, project_id="p1", chapter_id="c1")
        await _seed_project(socket_db_factory, project_id="p2", chapter_id="c2", status="ready")

        client_a = socketio_lib.AsyncSimpleClient()
        client_b = socketio_lib.AsyncSimpleClient()
        await client_a.connect(server, socketio_path="/socket.io")
        await client_b.connect(server, socketio_path="/socket.io")
        await asyncio.sleep(0.1)

        await client_a.emit("background:join", {"project_id": "p1"})
        snapshot_a = await _expect_background_joined_and_snapshot(client_a, "p1")

        await client_b.emit("background:join", {"project_id": "p2"})
        snapshot_b = await _expect_background_joined_and_snapshot(client_b, "p2")

        assert [item["chapter_id"] for item in snapshot_a["summary"]["statuses"]] == ["c1"]
        assert [item["chapter_id"] for item in snapshot_b["summary"]["statuses"]] == ["c2"]
        assert snapshot_b["summary"]["statuses"][0]["status"] == "ready"

        await emit(
            "background:task",
            {"project_id": "p1", "status": "done"},
            room=background_project_room("p1"),
        )
        event_a = await asyncio.wait_for(client_a.receive(), timeout=2.0)
        assert event_a[0] == "background:task"
        assert event_a[1] == {"project_id": "p1", "status": "done"}

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(client_b.receive(), timeout=0.3)

        await client_a.disconnect()
        await client_b.disconnect()
