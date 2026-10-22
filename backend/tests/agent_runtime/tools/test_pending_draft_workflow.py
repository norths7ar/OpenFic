"""AI continues the selected draft instead of creating incompatible parallel proposals."""

import asyncio
import json
from datetime import datetime

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.agent_runtime.tools.impls.project_change import (
    ProposeProjectUpdateTool,
    ReadPendingProjectChangeTool,
    RevisePendingProjectChangeTool,
)
from app.storage.models.note import Note
from app.storage.models.pending_project_change import (
    PendingProjectChange,
    PendingProjectChangeRevision,
)
from app.storage.models.project import Project
from app.storage.services import pending_project_change_apply_service as apply_service
from app.storage.services import pending_project_change_service as proposal_service
from tests.model_registry import register_sqlmodel_models

STATE = {"project_id": "review-project", "session_id": "review-session", "task_id": "writer"}


@pytest_asyncio.fixture
async def proposal_store(tmp_path, monkeypatch):
    register_sqlmodel_models()
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'proposals.db').as_posix()}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    async with factory() as session:
        session.add(Project(id=STATE["project_id"], title="提案并发"))
        session.add(
            Note(id="material", project_id=STATE["project_id"], title="正式稿", content="原文")
        )
        await session.commit()

    async def create_test_session():
        return factory()

    monkeypatch.setattr(
        "app.agent_runtime.tools.impls.project_change.create_session", create_test_session
    )
    try:
        yield factory
    finally:
        await engine.dispose()


async def _propose(call_id, body):
    tool = ProposeProjectUpdateTool(_state=STATE)
    return json.loads(
        await tool.ainvoke(
            {"target_type": "note", "target_id": "material", "body": body},
            config={"metadata": {"tool_call_id": call_id}},
        )
    )


async def _read(change_id):
    return json.loads(
        await ReadPendingProjectChangeTool(_state=STATE).ainvoke({"change_id": change_id})
    )


async def test_simultaneous_ai_proposals_redirect_to_one_draft_then_continue_its_text(
    proposal_store,
):
    # Independent database sessions contend for the same material; no mocked lock or repository.
    replies = await asyncio.wait_for(
        asyncio.gather(
            _propose("proposal-a", "草稿A：通知戒律司。"),
            _propose("proposal-b", "草稿B：通知戒律司。"),
        ),
        timeout=10,
    )
    winners = [r for r in replies if r["success"]]
    assert len(winners) == 1
    winner = winners[0]
    loser = next(r for r in replies if not r["success"])
    change_id = winner["pending_change_id"]
    assert loser["candidate_ids"] == [change_id]
    assert loser["action"] == "revise_pending_project_change"
    winner_index = replies.index(winner)
    retried = await _propose(
        ["proposal-a", "proposal-b"][winner_index],
        ["草稿A：通知戒律司。", "草稿B：通知戒律司。"][winner_index],
    )
    assert retried["pending_change_id"] == change_id

    first = await _read(change_id)
    amended = json.loads(
        await RevisePendingProjectChangeTool(_state=STATE).ainvoke(
            {
                "change_id": change_id,
                "expected_updated_at": first["updated_at"],
                "patch": {
                    "title": "自愿求援",
                    "edits": [{"old_content": "戒律司", "new_content": "飞瑶"}],
                },
            }
        )
    )
    assert amended["success"] is True
    assert amended["pending_change_id"] == change_id
    latest = await _read(change_id)
    assert latest["after"]["title"] == "自愿求援"
    assert latest["after"]["body"] == first["after"]["body"].replace("戒律司", "飞瑶")
    assert latest["current"]["body"] == "原文"
    async with proposal_store() as session:
        proposals = (await session.execute(select(PendingProjectChange))).scalars().all()
        versions = (await session.execute(select(PendingProjectChangeRevision))).scalars().all()
        assert [(p.id, p.status) for p in proposals] == [(change_id, "pending")]
        assert {v.id: v.after for v in versions} == {
            first["current_revision_id"]: first["after"],
            latest["current_revision_id"]: latest["after"],
        }
        assert all(v.source == "ai" for v in versions)
        assert (await session.get(Note, "material")).content == "原文"


async def test_existing_parallel_drafts_remain_separate_until_user_selects_one(proposal_store):
    created = await _propose("existing-a", "版本A")
    first_id = created["pending_change_id"]
    # Represent duplicates already present before the single-draft rule; normal creation
    # must not create this state, but reviewing existing data must not discard either draft.
    async with proposal_store() as session:
        first = await session.get(PendingProjectChange, first_id)
        second = PendingProjectChange(
            **first.model_dump(exclude={"id", "after", "current_revision_id"}),
            id="existing-b",
            after={**first.after, "body": "版本B"},
            current_revision_id="existing-b-v1",
        )
        session.add(second)
        await session.flush()
        session.add(
            PendingProjectChangeRevision(
                id="existing-b-v1", change_id=second.id, after=second.after, source="migration"
            )
        )
        await session.commit()

    blocked = await _propose("new-parallel", "不应创建的第三稿")
    assert blocked["success"] is False
    assert set(blocked["candidate_ids"]) == {first_id, "existing-b"}
    before = await _read(first_id)
    selected = await _read("existing-b")
    assert before["after"]["body"] == "版本A"
    assert selected["after"]["body"] == "版本B"
    async with proposal_store() as session:
        chosen = await proposal_service.get_pending_change(
            session, STATE["project_id"], "existing-b"
        )
        await apply_service.apply_pending_change(
            session,
            chosen,
            expected_updated_at=datetime.fromisoformat(selected["updated_at"]),
            expected_current_hash=selected["current_hash"],
            revision_id=selected["current_revision_id"],
        )
        await session.commit()

    remaining = await _read(first_id)
    assert remaining["status"] == "pending"
    assert remaining["after"] == before["after"]
    assert remaining["current"]["body"] == "版本B"
    async with proposal_store() as session:
        proposals = (await session.execute(select(PendingProjectChange))).scalars().all()
        assert {p.id: p.status for p in proposals} == {first_id: "pending", "existing-b": "applied"}
