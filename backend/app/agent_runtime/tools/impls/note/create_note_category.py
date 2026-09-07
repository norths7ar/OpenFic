"""
创建笔记分类。
"""

import json
from typing import Any

from pydantic import BaseModel, Field

from app.agent_runtime.revisions import (
    current_revision_id_from_state,
    note_category_images_by_id,
    record_note_category_diffs,
)
from app.agent_runtime.tools.base import AgentTool
from app.agent_runtime.tools.errors import ToolExecutionError
from app.agent_runtime.tools.impls._locks import keyed_lock
from app.agent_runtime.tools.registry import ToolRegistry
from app.storage.database import create_session
from app.storage.models.project_folder import ProjectFolder
from app.storage.repos import note_category_repo


class CreateNoteCategoryInput(BaseModel):
    title: str = Field(description="分类标题")
    parent_ref: dict | None = Field(
        default=None, description="兼容字段，单层文件夹不允许指定父分类"
    )


@ToolRegistry.register
class CreateNoteCategoryTool(AgentTool):
    name: str = "create_note_category"
    description: str = "创建单层笔记文件夹，同名通过 ID 区分"
    access_level: str = "write"
    args_schema: type[BaseModel] = CreateNoteCategoryInput

    async def build_interrupt_preview(self, args: dict[str, Any]) -> dict | None:
        session = self.get_runtime_db_session()
        title = args.get("title")
        parent_ref = args.get("parent_ref")
        if (
            session is None
            or not isinstance(title, str)
            or (parent_ref is not None and not isinstance(parent_ref, dict))
        ):
            return None
        if parent_ref is not None:
            return None
        parent_id = None
        return {
            "type": "preview",
            "success": True,
            "reason": "approval_preview",
            "metadata": {"category": {"title": title, "parent_id": parent_id}},
        }

    async def _execute(
        self,
        title: str,
        parent_ref: dict | None = None,
    ) -> str:
        revision_id = current_revision_id_from_state(self._state)
        if revision_id is None:
            raise ToolExecutionError("缺少当前 revision，无法执行分类创建")
        session = await create_session()
        try:
            if parent_ref is not None:
                raise ToolExecutionError("文件夹只能存在一层，不能指定父文件夹")
            parent_id = None

            async with await keyed_lock((self.project_id, parent_id)):
                before = note_category_images_by_id(
                    await note_category_repo.list_by_project(session, self.project_id)
                )
                next_order = (
                    max(
                        (category.order for category in before.values()),
                        default=0,
                    )
                    + 1
                )

                category = ProjectFolder(
                    project_id=self.project_id,
                    scope="note",
                    title=title,
                    order=next_order,
                )
                category = await note_category_repo.create(session, category)
                after = note_category_images_by_id(
                    await note_category_repo.list_by_project(session, self.project_id)
                )
                await record_note_category_diffs(
                    session,
                    revision_id=revision_id,
                    project_id=self.project_id,
                    before=before,
                    after=after,
                )

                from app.background.jobs import service as background_service

                await background_service.commit_and_notify(session)
                return json.dumps(
                    {
                        "success": True,
                        "metadata": {
                            "category": {
                                "id": category.id,
                                "title": category.title,
                                "parent_id": None,
                            }
                        },
                    },
                    ensure_ascii=False,
                )
        except ToolExecutionError:
            raise
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
