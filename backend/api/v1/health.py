"""Health and readiness check endpoints."""
import asyncio

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.config import settings
from ...core.database import get_db

router = APIRouter()


@router.get("/health")
async def health():
    """Lightweight liveness probe."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(db: AsyncSession = Depends(get_db)):
    """Full readiness: checks DB, NAM, and NNLM connectivity."""
    checks: dict[str, dict] = {}

    # Postgres
    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = {"ok": True}
    except Exception as exc:
        checks["postgres"] = {"ok": False, "error": str(exc)}

    # NAM and NNLM — fire in parallel
    async def _ping(name: str, url: str) -> tuple[str, dict]:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(url)
                return name, {"ok": r.status_code < 500, "status_code": r.status_code}
        except Exception as exc:
            return name, {"ok": False, "error": str(exc)}

    probes = [
        _ping("nam_query", f"{settings.nam_query_url}/health"),
        _ping("nnlm_encoder", f"{settings.nnlm_encoder_url}/health"),
        _ping("nnlm_decoder", f"{settings.nnlm_decoder_url}/health"),
    ]
    results = await asyncio.gather(*probes)
    for name, result in results:
        checks[name] = result

    all_ok = all(v["ok"] for v in checks.values())
    return {"status": "ready" if all_ok else "degraded", "checks": checks}
