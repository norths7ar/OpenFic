"""错误传播测试。"""

import pytest

from app.agent_runtime.persistence.errors import (
    PersistenceLoadError,
)
from app.agent_runtime.persistence.loader import load_history


class _BrokenSession:
    async def execute(self, *_a, **_kw):
        raise RuntimeError("DB down")

    async def commit(self):
        raise RuntimeError("DB down")

    async def rollback(self):
        return None

    async def close(self):
        return None

    def add(self, *_a, **_kw):
        return None

    async def get(self, *_a, **_kw):
        raise RuntimeError("DB down")

    async def refresh(self, *_a, **_kw):
        return None


@pytest.mark.asyncio
async def test_load_history_propagates_load_error():
    with pytest.raises(PersistenceLoadError):
        await load_history(_BrokenSession(), "session_a")  # type: ignore[arg-type]
