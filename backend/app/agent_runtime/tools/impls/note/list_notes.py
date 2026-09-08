"""
列出某分类下的直接子项（笔记 + 子分类）。
"""

import json

from pydantic import BaseModel, Field

from app.agent_runtime.context.knowledge_visibility import (
    get_knowledge_scope,
    note_is_visible,
)
from app.agent_runtime.tools.base import AgentTool
from app.agent_runtime.tools.registry import ToolRegistry
from app.storage.database import create_session
from app.storage.repos import note_category_repo, note_repo


class ListNotesInput(BaseModel):
    path: str = Field(
        default="/",
        description="文件夹路径，如 / 或 /设定。'/' 表示根目录；文件夹仅一层",
    )


@ToolRegistry.register
class ListNotesTool(AgentTool):
    name: str = "list_notes"
    description: str = "列出根目录或单层笔记文件夹中的直接笔记。'/' 会同时返回笔记文件夹"
    access_level: str = "readonly"
    args_schema: type[BaseModel] = ListNotesInput

    async def _execute(self, path: str = "/") -> str:
        session = await create_session()
        try:
            categories = await note_category_repo.list_by_project(session, self.project_id, "note")
            notes = await note_repo.list_by_project(session, self.project_id, include_hidden=False)
            scope = get_knowledge_scope(self._state)
            notes = [note for note in notes if note_is_visible(note, scope=scope)]

            target_category_id: str | None
            if path == "/":
                target_category_id = None
            else:
                segments = [s for s in path.strip("/").split("/") if s]
                if len(segments) != 1:
                    return json.dumps({"error": f"文件夹仅支持一层: {path}"}, ensure_ascii=False)
                matches = [category for category in categories if category.title == segments[0]]
                if not matches:
                    return json.dumps({"error": f"未找到路径: {path}"}, ensure_ascii=False)
                if len(matches) > 1:
                    return json.dumps(
                        {"error": f"文件夹名称不唯一，请使用根目录或 ID 引用: {path}"},
                        ensure_ascii=False,
                    )
                target_category_id = matches[0].id

            sub_categories = categories if target_category_id is None else []
            sub_notes = [n for n in notes if n.category_id == target_category_id]

            items: list[dict] = []
            for cat in sorted(sub_categories, key=lambda c: c.title):
                items.append(
                    {"type": "category", "id": cat.id, "title": cat.title, "scope": cat.scope}
                )
            for note in sorted(sub_notes, key=lambda n: n.title):
                items.append({"type": "note", "id": note.id, "title": note.title})

            return json.dumps({"path": path, "scope": "note", "items": items}, ensure_ascii=False)
        finally:
            await session.close()
