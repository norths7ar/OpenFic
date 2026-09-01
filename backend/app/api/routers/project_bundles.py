from typing import Literal, cast
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.project_bundle.apply import BundleApplyConflictError, apply_project_bundle
from app.project_bundle.archive import BundleFormatError
from app.project_bundle.export import export_project_bundle
from app.project_bundle.importer import preview_project_bundle
from app.project_bundle.mapped_bundle import (
    build_mapped_project_bundle,
    persist_mapped_import_bindings,
    persist_source_mapping_profile,
)
from app.project_bundle.names import slugify_filename
from app.project_bundle.source_export import export_markdown_source_bundle
from app.project_bundle.source_mapping import (
    MappedSourceItem,
    read_source_mapping_manifest,
)
from app.storage.database import get_session
from app.storage.models.project import Project

router = APIRouter(tags=["project-bundles"])
MAX_BUNDLE_UPLOAD_BYTES = 60 * 1024 * 1024


async def _read_bundle_upload(file: UploadFile) -> bytes:
    data = await file.read(MAX_BUNDLE_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件为空")
    if len(data) > MAX_BUNDLE_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Bundle 文件过大",
        )
    return data


def _source_item_response(item: MappedSourceItem) -> dict:
    return {
        "source": item.source,
        "rule_id": item.rule_id,
        "target": item.target,
        "anchor": item.anchor,
        "title": item.title,
        "section": item.section,
        "category_path": item.category_path,
        "writing_visible": item.writing_visible,
        "order": item.order,
    }


@router.get("/projects/{project_id}/bundle/export")
async def export_bundle(
    project_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> Response:
    try:
        project = await session.get(Project, project_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
        data = await export_project_bundle(session, project_id)
    except BundleFormatError as exc:
        if str(exc).startswith("project not found:"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
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


@router.get("/projects/{project_id}/bundle/source/export")
async def export_source_bundle(
    project_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> Response:
    try:
        project = await session.get(Project, project_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
        data = await export_markdown_source_bundle(session, project_id)
    except BundleFormatError as exc:
        if str(exc).startswith("project not found:"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    project_name = slugify_filename(project.title, project_id)
    display_filename = f"{project_name}.markdown.zip"
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                'attachment; filename="openfic-markdown-source.zip"; '
                f"filename*=UTF-8''{quote(display_filename, safe='')}"
            )
        },
    )


@router.post("/projects/{project_id}/bundle/import/preview")
async def preview_bundle_import(
    project_id: str,
    file: UploadFile = File(...),  # noqa: B008
    mode: str = Form(default="merge"),
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict:
    data = await _read_bundle_upload(file)
    try:
        preview = await preview_project_bundle(
            session, project_id, data, cast(Literal["append", "update", "merge"], mode)
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BundleFormatError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "mode": preview.mode,
        "source_project": preview.source_project,
        "items": [item.__dict__ for item in preview.items],
        "summary": preview.summary,
    }


@router.post("/projects/{project_id}/bundle/import/apply")
async def apply_bundle_import(
    project_id: str,
    file: UploadFile = File(...),  # noqa: B008
    mode: str = Form(default="merge"),
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict:
    data = await _read_bundle_upload(file)
    try:
        result = await apply_project_bundle(
            session, project_id, data, cast(Literal["append", "update", "merge"], mode)
        )
        await session.commit()
    except BundleApplyConflictError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(exc),
                "conflicts": [item.__dict__ for item in exc.items],
            },
        ) from exc
    except NotFoundError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BundleFormatError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception:
        await session.rollback()
        raise
    return {
        "mode": result.mode,
        "items": [item.__dict__ for item in result.items],
        "summary": result.summary,
    }


@router.post("/projects/{project_id}/bundle/source/preview")
async def preview_source_bundle_import(
    project_id: str,
    file: UploadFile = File(...),  # noqa: B008
    mode: str = Form(default="merge"),
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict:
    data = await _read_bundle_upload(file)
    try:
        mapped = await build_mapped_project_bundle(session, project_id, data)
        preview = await preview_project_bundle(
            session,
            project_id,
            mapped.data,
            cast(Literal["append", "update", "merge"], mode),
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BundleFormatError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "mode": preview.mode,
        "source_items": [_source_item_response(item) for item in mapped.source_items],
        "items": [item.__dict__ for item in preview.items],
        "summary": preview.summary,
    }


@router.post("/projects/{project_id}/bundle/source/apply")
async def apply_source_bundle_import(
    project_id: str,
    file: UploadFile = File(...),  # noqa: B008
    mode: str = Form(default="merge"),
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict:
    data = await _read_bundle_upload(file)
    try:
        mapped = await build_mapped_project_bundle(session, project_id, data)
        result = await apply_project_bundle(
            session,
            project_id,
            mapped.data,
            cast(Literal["append", "update", "merge"], mode),
        )
        await persist_mapped_import_bindings(session, project_id, mapped.bindings)
        _, mapping_yaml = read_source_mapping_manifest(data, project_id)
        await persist_source_mapping_profile(session, project_id, mapping_yaml)
        await session.commit()
    except BundleApplyConflictError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(exc),
                "conflicts": [item.__dict__ for item in exc.items],
            },
        ) from exc
    except NotFoundError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BundleFormatError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception:
        await session.rollback()
        raise
    return {
        "mode": result.mode,
        "source_items": [_source_item_response(item) for item in mapped.source_items],
        "items": [item.__dict__ for item in result.items],
        "summary": result.summary,
    }
