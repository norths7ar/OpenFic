from collections.abc import Sequence
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, field_validator

from app.agent_runtime.tools.errors import ToolExecutionError


class ChapterRef(BaseModel):
    type: Literal["order", "title"] = Field(
        description="章节定位方式：order 表示卷内章节序号，title 表示章节标题",
    )
    value: int | str = Field(
        description="与 type 对应的章节定位值；type 为 order 时传入整数序号，type 为 title 时传入精确的章节标题",
    )

    @field_validator("value", mode="before")
    @classmethod
    def coerce_value(cls, v: Any, info: Any) -> int | str:
        if info.data.get("type") == "order":
            return int(v)
        return str(v)


class VolumeRef(BaseModel):
    type: Literal["order", "title"] = Field(
        description="卷定位方式：order 表示卷序号，title 表示卷标题",
    )
    value: int | str = Field(
        description="与 type 对应的卷定位值；type 为 order 时传入整数序号，type 为 title 时传入精确的卷标题",
    )

    @field_validator("value", mode="before")
    @classmethod
    def coerce_value(cls, v: Any, info: Any) -> int | str:
        if info.data.get("type") == "order":
            return int(v)
        return str(v)


class _OrderedTitled(Protocol):
    order: int
    title: str


def resolve_volume_from_list[TOrderedTitled: _OrderedTitled](
    volumes: Sequence[TOrderedTitled],
    ref: VolumeRef,
) -> TOrderedTitled:
    if ref.type == "order":
        match = next((volume for volume in volumes if volume.order == ref.value), None)
    else:
        match = next((volume for volume in volumes if volume.title == ref.value), None)
    if match is None:
        raise ToolExecutionError(f"未找到卷: {ref.type}={ref.value}")
    return match


def resolve_chapter_from_list[TOrderedTitled: _OrderedTitled](
    chapters: Sequence[TOrderedTitled],
    ref: ChapterRef,
) -> TOrderedTitled:
    if ref.type == "order":
        match = next((chapter for chapter in chapters if chapter.order == ref.value), None)
    else:
        match = next((chapter for chapter in chapters if chapter.title == ref.value), None)
    if match is None:
        raise ToolExecutionError(f"未找到章节: {ref.type}={ref.value}")
    return match
