from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.agent_runtime.tools.base import HookContext
from app.agent_runtime.tools.hooks.auth import auth_hook


def _mock_db_session() -> SimpleNamespace:
    return SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None))
    )


def _make_context(access_level: str = "write", tool_name: str = "test") -> HookContext:
    return HookContext(
        tool_name=tool_name,
        access_level=access_level,
        args={"some": "arg"},
        state={"session_id": "s1", "project_id": "p1"},
        config={"configurable": {"db_session": _mock_db_session()}},
    )


def _patch_permissions(permissions: dict[str, str]):
    return patch(
        "app.agent_runtime.tools.hooks.auth._read_user_permissions",
        new=AsyncMock(return_value=permissions),
    )


async def test_global_bypass_allows_write_without_approval():
    with (
        patch(
            "app.agent_runtime.tools.hooks.auth.setting_repo.get_by_key",
            new=AsyncMock(return_value=SimpleNamespace(value="true")),
        ),
        _patch_permissions({"write_chapter": "ask"}),
    ):
        result = await auth_hook(_make_context(tool_name="write_chapter", access_level="write"))
    assert result.proceed is True
    assert result.interrupt_payload is None
