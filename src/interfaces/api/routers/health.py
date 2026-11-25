import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db.session import get_session

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(session: Annotated[AsyncSession, Depends(get_session)]) -> JSONResponse:
    checks = {"db": False}
    try:
        await session.execute(text("SELECT 1"))
        checks["db"] = True
    except Exception:
        logger.exception("readiness: db check failed")

    ok = all(checks.values())
    return JSONResponse(status_code=200 if ok else 503, content=checks)
