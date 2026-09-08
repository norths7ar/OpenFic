"""Typed ORM boundary for material visibility, including rollback snapshots."""

from typing import Any, cast

from sqlalchemy import Enum as SQLAlchemyEnum
from sqlmodel import Field, SQLModel

from app.core.agent_visibility import AgentVisibility


class AgentVisibilityType(SQLAlchemyEnum):
    # Persist public values ("all"), not Python member names ("ALL"). SQLite
    # keeps its existing text storage; invalid ORM binds/loads are rejected.
    def __init__(self, *enums: object, **kwargs: Any) -> None:
        if enums:
            # SQLAlchemy creates dialect-adapted copies with its stored enum
            # values. Let that constructor path keep its supplied settings.
            super().__init__(*cast(tuple[Any, ...], enums), **kwargs)
        else:
            super().__init__(
                AgentVisibility,
                values_callable=lambda enum: [member.value for member in enum],
                native_enum=False,
                create_constraint=False,
                validate_strings=True,
                length=32,
            )


class _AgentVisibilityModel(SQLModel):
    @staticmethod
    def _coerce_visibility(value: Any) -> AgentVisibility | None:
        return AgentVisibility(value)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "agent_visibility":
            # SQLModel writes instrumented attributes before Pydantic assignment
            # validation. Validate first so a failed assignment leaves no dirty
            # invalid value behind. This also covers table-model construction.
            value = self._coerce_visibility(value)
        super().__setattr__(name, value)


class AgentVisibilityModel(_AgentVisibilityModel):
    agent_visibility: AgentVisibility = Field(
        default=AgentVisibility.ALL,
        sa_type=AgentVisibilityType,
        index=True,
    )


class AgentVisibilitySnapshotModel(_AgentVisibilityModel):
    agent_visibility: AgentVisibility | None = Field(
        default=None,
        sa_type=AgentVisibilityType,
    )

    @staticmethod
    def _coerce_visibility(value: Any) -> AgentVisibility | None:
        # Nonexistent-object snapshots have no material state to store.
        return None if value is None else AgentVisibility(value)
