from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.database import get_session_factory

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", response_model=None)
async def readiness() -> dict[str, object] | JSONResponse:
    components: dict[str, str] = {"postgres": "unavailable"}
    try:
        async with get_session_factory()() as session:
            await session.execute(text("SELECT 1"))
        components["postgres"] = "ready"
    except Exception as exc:
        logger.warning("readiness_postgres_failed", extra={"error_type": type(exc).__name__})
    if all(value == "ready" for value in components.values()):
        return {"status": "ready", "components": components}
    return JSONResponse(
        status_code=503,
        content={"status": "not_ready", "components": components},
    )
