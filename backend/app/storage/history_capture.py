"""SQLite recovery capture shared by ORM, bulk writes and imports.

Triggers run in the mutation transaction. The SQLAlchemy event copies the
operation source before each statement; the SQLite worker never reads ContextVar.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps

from sqlalchemy import event, inspect
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel

from app.storage.models.document_history import DocumentHistory

_source = ContextVar("document_history_source", default="manual")


@contextmanager
def history_source(source: str):
    token = _source.set(source)
    try:
        yield
    finally:
        _source.reset(token)


def with_history_source(source: str):
    def decorate(function):
        @wraps(function)
        async def wrapped(*args, **kwargs):
            with history_source(source):
                return await function(*args, **kwargs)

        return wrapped

    return decorate


@event.listens_for(Engine, "connect")
def _register_source(connection, record):
    state = {"source": "manual"}
    record.info["document_history_source"] = state
    connection.create_function("openfic_history_source", 0, lambda: state["source"])


@event.listens_for(Engine, "before_cursor_execute")
def _copy_source(connection, cursor, statement, parameters, context, executemany):
    state = connection.info.get("document_history_source")
    if state is not None:
        state["source"] = _source.get()


def install_capture(connection):
    """Install v1 recovery triggers. Also used by isolated metadata-created tests."""
    from app.storage.migrations.history_v1 import install

    install(connection)


@event.listens_for(SQLModel.metadata, "after_create")
def _install_on_create(metadata, connection, **kwargs):
    tables = set(inspect(connection).get_table_names())
    if {
        DocumentHistory.__tablename__,
        "document_trash",
        "chapters",
        "notes",
        "characters",
        "world_info_entries",
        "projects",
    } <= tables:
        install_capture(connection)
