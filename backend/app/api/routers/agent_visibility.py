"""Visibility catalog shared by all material controls."""

from dataclasses import asdict

from fastapi import APIRouter

from app.core.agent_visibility import AGENT_VISIBILITY_STATES, DEFAULT_AGENT_VISIBILITY

router = APIRouter(tags=["agent-visibility"])


@router.get("/agent-visibility")
async def get_agent_visibility_catalog() -> dict:
    return {
        "default": DEFAULT_AGENT_VISIBILITY,
        "states": [asdict(state) for state in AGENT_VISIBILITY_STATES],
    }
