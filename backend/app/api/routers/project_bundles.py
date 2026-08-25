from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.project_bundle.archive import BundleFormatError
from app.project_bundle.export import export_project_bundle
from app.project_bundle.names import slugify_filename
from app.storage.database import get_session
from app.storage.models.project import Project

router = APIRouter(tags=["project-bundles"])


@router.get("/projects/{project_id}/bundle/export")
async def export_bundle(
    project_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> Response:
    try:
        project = await session.get(Project, project_id)
        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在"
            )
        data = await export_project_bundle(session, project_id)
    except BundleFormatError as exc:
        if str(exc).startswith("project not found:"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    project_name = slugify_filename(project.title, project_id)
    display_filename = f"{project_name}.openfic.zip"
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                'attachment; filename="openfic-project-bundle.zip"; '
                f"filename*=UTF-8''{quote(display_filename, safe='')}"
            )
        },
    )
