"""Document history and recycle-bin endpoints."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.background.jobs import service as background_service
from app.storage.database import get_session
from app.storage.services import document_history_service as service

router = APIRouter(tags=["document-history"])
Session = Annotated[AsyncSession, Depends(get_session)]
PREFIX = "/projects/{project_id}/documents/{kind}/{document_id}/history"


class RestoreRequest(BaseModel):
    base_updated_at: datetime


def history_response(item, *, detail=False):
    result = {
        "id": item.id,
        "document_id": item.document_id,
        "kind": item.kind,
        "title": item.title,
        "source": item.source,
        "created_at": service.utc(item.created_at),
    }
    if detail:
        result["content"] = item.content
    return result


@router.get(PREFIX)
async def list_history(
    project_id: str, kind: service.DocumentKind, document_id: str, session: Session
):
    items, updated_at = await service.history_list(
        session, project_id, kind, document_id, metadata_only=True
    )
    return {"items": [history_response(item) for item in items], "current_updated_at": updated_at}


@router.get(PREFIX + "/{history_id}")
async def get_history(
    project_id: str, kind: service.DocumentKind, document_id: str, history_id: str, session: Session
):
    item = await service.history_detail(session, project_id, kind, document_id, history_id)
    return history_response(item, detail=True)


@router.post(PREFIX + "/{history_id}/restore")
async def restore_history(
    project_id: str,
    kind: service.DocumentKind,
    document_id: str,
    history_id: str,
    data: RestoreRequest,
    session: Session,
):
    await service.restore_history(
        session, project_id, kind, document_id, history_id, data.base_updated_at
    )
    await background_service.commit_and_notify(session)
    return {"document_id": document_id, "kind": kind}


@router.get("/projects/{project_id}/trash")
async def list_trash(project_id: str, session: Session):
    items = await service.trash_list(session, project_id)
    return {
        "items": [
            {
                "id": item.id,
                "document_id": item.document_id,
                "kind": item.kind,
                "title": item.title,
                "content": item.content,
                "deleted_at": service.utc(item.deleted_at),
            }
            for item in items
        ]
    }


@router.post("/projects/{project_id}/trash/{trash_id}/restore")
async def restore_trash(project_id: str, trash_id: str, session: Session):
    document_id, kind = await service.restore_trash(session, project_id, trash_id)
    await background_service.commit_and_notify(session)
    return {"document_id": document_id, "kind": kind}


@router.delete("/projects/{project_id}/trash/{trash_id}", status_code=204)
async def delete_trash(project_id: str, trash_id: str, session: Session):
    await service.delete_trash(session, project_id, trash_id)
    await background_service.commit_and_notify(session)
    return Response(status_code=204)
