"""Sync event log query endpoints."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...db.models import SyncEvent

router = APIRouter()


@router.get("/sync-events")
async def list_sync_events(
    pipeline_id: str | None = Query(None),
    status: str | None = Query(None),
    entity_name: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    q = select(SyncEvent).order_by(desc(SyncEvent.synced_at))
    if pipeline_id:
        q = q.where(SyncEvent.pipeline_id == pipeline_id)
    if status:
        q = q.where(SyncEvent.status == status)
    if entity_name:
        q = q.where(SyncEvent.entity_name == entity_name)
    q = q.offset(offset).limit(limit)

    result = await db.execute(q)
    rows = result.scalars().all()
    return {"items": [_ser(e) for e in rows], "limit": limit, "offset": offset}


@router.get("/sync-events/{event_id}")
async def get_sync_event(event_id: str, db: AsyncSession = Depends(get_db)):
    from fastapi import HTTPException
    result = await db.execute(select(SyncEvent).where(SyncEvent.id == event_id))
    e = result.scalar_one_or_none()
    if not e:
        raise HTTPException(status_code=404, detail="Sync event not found")
    return _ser(e)


@router.get("/sync-events/stats/summary")
async def sync_event_summary(
    pipeline_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate counts by status for the monitoring dashboard."""
    from sqlalchemy import func
    q = select(SyncEvent.status, func.count(SyncEvent.id).label("count"))
    if pipeline_id:
        q = q.where(SyncEvent.pipeline_id == pipeline_id)
    q = q.group_by(SyncEvent.status)

    result = await db.execute(q)
    rows = result.all()
    summary = {row.status: row.count for row in rows}
    return {
        "success": summary.get("success", 0),
        "failed": summary.get("failed", 0),
        "skipped": summary.get("skipped", 0),
        "total": sum(summary.values()),
    }


def _ser(e: SyncEvent) -> dict:
    return {
        "id": e.id,
        "pipeline_id": e.pipeline_id,
        "entity_name": e.entity_name,
        "direction": e.direction,
        "status": e.status,
        "record_id": e.record_id,
        "error_message": e.error_message,
        "payload_hash": e.payload_hash,
        "synced_at": e.synced_at.isoformat() if e.synced_at else None,
    }
