from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Hashable, Iterable
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.repos import pending_project_change_repo

_LOCKS: dict[Hashable, asyncio.Lock] = {}
_GUARD = asyncio.Lock()


async def keyed_lock(key: Hashable) -> asyncio.Lock:
    async with _GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _LOCKS[key] = lock
        return lock


@asynccontextmanager
async def keyed_locks(keys: Iterable[Hashable]) -> AsyncIterator[None]:
    locks = [await keyed_lock(key) for key in sorted(set(keys), key=repr)]
    acquired: list[asyncio.Lock] = []
    try:
        for lock in locks:
            await lock.acquire()
            acquired.append(lock)
        yield
    finally:
        for lock in reversed(acquired):
            lock.release()


@asynccontextmanager
async def project_write_lock(
    session: AsyncSession, project_id: str, *, scopes: Iterable[str]
) -> AsyncIterator[None]:
    # Acquire all tool locks before opening the write transaction. Proposal apply
    # uses the same database lock; take it before reading any editable state.
    async with keyed_locks((scope, project_id) for scope in scopes):
        try:
            await pending_project_change_repo.lock_project(session, project_id)
            yield
        except BaseException:
            # Roll back failures (including cancellation) before admitting the
            # next tool, so it cannot wait on our still-open database transaction.
            await session.rollback()
            raise
