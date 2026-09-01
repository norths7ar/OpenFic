"""全局异常处理器测试。"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.exceptions import register_exception_handlers
from app.core.errors import ConflictError, NotFoundError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (NotFoundError("missing"), 404),
        (ValueError("invalid"), 400),
        (ConflictError("conflict"), 409),
    ],
)
async def test_domain_errors_use_public_http_contract(
    error: Exception,
    expected_status: int,
) -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise error

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")

    assert response.status_code == expected_status
    assert response.json() == {"detail": str(error)}


@pytest.mark.asyncio
async def test_unhandled_exception_returns_generic_500() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal Server Error"}
