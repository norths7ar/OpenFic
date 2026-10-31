"""
Health check response schemas.
"""

from typing import Literal

from app.api.schemas.base import APIModel


class HealthResponse(APIModel):
    """Health check response."""

    status: str
    version: str


class MaintenanceResponse(APIModel):
    """Local database maintenance status."""

    status: Literal["pending", "running", "ready", "failed"]
    phase: str
    progress: float | None
    deleted_rows: int
    reclaimed_pages: int
    total_pages: int
    elapsed_seconds: float
    message: str
    error: str | None
