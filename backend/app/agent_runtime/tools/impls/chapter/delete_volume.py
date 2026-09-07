import json

from pydantic import BaseModel, Field

from app.agent_runtime.tools.base import AgentTool
from app.agent_runtime.tools.impls.chapter.refs import VolumeRef, resolve_volume_from_list
from app.agent_runtime.tools.registry import ToolRegistry
from app.storage.database import create_session
from app.storage.repos import volume_repo
from app.storage.services import volume_service
from app.storage.services.version_control_service import refresh_project_stats


class DeleteVolumeInput(BaseModel):
    volume_ref: VolumeRef = Field(description="目标卷")
    cascade: bool = Field(
        default=False,
        description="兼容字段；删除文件夹始终保留章节并移回根目录",
    )


@ToolRegistry.register
class DeleteVolumeTool(AgentTool):
    name: str = "delete_volume"
    description: str = "删除指定卷"
    access_level: str = "write"
    args_schema: type[BaseModel] = DeleteVolumeInput

    async def _execute(self, volume_ref: dict, cascade: bool = False) -> str:
        session = await create_session()
        try:
            volume = resolve_volume_from_list(
                await volume_repo.list_by_project(session, self.project_id),
                VolumeRef.model_validate(volume_ref),
            )
            await volume_service.delete_volume(session, volume.id, cascade=cascade)
            await refresh_project_stats(session, self.project_id)
            await session.commit()
            return json.dumps(
                {
                    "success": True,
                },
                ensure_ascii=False,
            )
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
