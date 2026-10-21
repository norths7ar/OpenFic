from datetime import UTC, datetime
from typing import Literal

from app.agent_runtime.context.compaction.overlay import apply_compaction_overlay
from app.agent_runtime.context.types import ContextMessage
from app.agent_runtime.persistence.compaction_types import PersistedCompaction

ContextRole = Literal["system", "user", "assistant", "tool"]


def history(role: ContextRole, content: str, seq: int, **kwargs) -> ContextMessage:
    return ContextMessage(
        role=role,
        content=content,
        metadata={"part": "history", "seq": seq},
        **kwargs,
    )  # type: ignore[arg-type]


def compaction(start: int, end: int, summary: str = "摘要") -> PersistedCompaction:
    return PersistedCompaction(
        id=f"c-{start}-{end}",
        session_id="s1",
        task_id="t1",
        project_id="p1",
        start_seq=start,
        end_seq=end,
        summary=summary,
        trigger="auto",
        source_input_tokens=3000,
        summary_tokens=20,
        created_at=datetime.now(UTC),
    )


def test_overlay_replaces_range_with_wrapped_user_summary() -> None:
    messages = [
        history("user", "first", 1),
        history("assistant", "old answer", 2),
        history("user", "old followup", 3),
        history("assistant", "new answer", 4),
        ContextMessage(role="system", content="static", metadata={"part": "rules"}),
    ]

    out = apply_compaction_overlay(messages, [compaction(2, 3, "压缩摘要")])

    assert [(m.role, m.content) for m in out] == [
        ("user", "first"),
        ("user", "<compaction-summary>\n压缩摘要\n</compaction-summary>"),
        ("assistant", "new answer"),
        ("system", "static"),
    ]
    assert out[1].metadata == {"part": "history", "compaction_id": "c-2-3"}
