"""Pipeline CRUD, start/pause/run endpoints."""
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...db.models import Pipeline, PipelineRun, PipelineStatus, SyncDirection

router = APIRouter()


class PipelineCreate(BaseModel):
    name: str
    description: str = ""
    source_connector_id: str
    target_connector_id: str
    entity_name: str
    direction: str = "bidirectional"
    poll_interval_seconds: int = 300
    use_cdc: bool = False


class PipelineUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    poll_interval_seconds: int | None = None
    direction: str | None = None


@router.get("")
async def list_pipelines(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Pipeline).order_by(Pipeline.created_at.desc()))
    rows = result.scalars().all()
    return {"items": [_serialize(p) for p in rows]}


@router.get("/{pipeline_id}")
async def get_pipeline(pipeline_id: str, db: AsyncSession = Depends(get_db)):
    p = await _get_or_404(pipeline_id, db)
    return _serialize(p)


@router.post("", status_code=201)
async def create_pipeline(body: PipelineCreate, db: AsyncSession = Depends(get_db)):
    pipeline = Pipeline(
        id=str(uuid.uuid4()),
        name=body.name,
        description=body.description,
        source_connector_id=body.source_connector_id,
        target_connector_id=body.target_connector_id,
        entity_name=body.entity_name,
        direction=SyncDirection(body.direction),
        poll_interval_seconds=body.poll_interval_seconds,
        use_cdc=body.use_cdc,
        status=PipelineStatus.DRAFT,
    )
    db.add(pipeline)
    await db.commit()
    await db.refresh(pipeline)
    return _serialize(pipeline)


@router.put("/{pipeline_id}")
async def update_pipeline(pipeline_id: str, body: PipelineUpdate, db: AsyncSession = Depends(get_db)):
    p = await _get_or_404(pipeline_id, db)
    if body.name is not None:
        p.name = body.name
    if body.description is not None:
        p.description = body.description
    if body.poll_interval_seconds is not None:
        p.poll_interval_seconds = body.poll_interval_seconds
    if body.direction is not None:
        p.direction = SyncDirection(body.direction)
    p.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(p)
    return _serialize(p)


@router.delete("/{pipeline_id}", status_code=204)
async def delete_pipeline(pipeline_id: str, db: AsyncSession = Depends(get_db)):
    p = await _get_or_404(pipeline_id, db)
    await db.delete(p)
    await db.commit()


@router.post("/{pipeline_id}/start")
async def start_pipeline(pipeline_id: str, db: AsyncSession = Depends(get_db)):
    p = await _get_or_404(pipeline_id, db)
    p.status = PipelineStatus.ACTIVE
    p.updated_at = datetime.utcnow()
    await db.commit()
    return {"status": "active", "pipeline_id": pipeline_id}


@router.post("/{pipeline_id}/pause")
async def pause_pipeline(pipeline_id: str, db: AsyncSession = Depends(get_db)):
    p = await _get_or_404(pipeline_id, db)
    p.status = PipelineStatus.PAUSED
    p.updated_at = datetime.utcnow()
    await db.commit()
    return {"status": "paused", "pipeline_id": pipeline_id}


@router.post("/{pipeline_id}/run")
async def run_pipeline_now(
    pipeline_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    p = await _get_or_404(pipeline_id, db)

    async def _run():
        from ...pipeline.runner import PipelineRunner
        from ...core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            runner = PipelineRunner(session)
            await runner.run(p, trigger="manual")

    background_tasks.add_task(_run)
    return {"status": "triggered", "pipeline_id": pipeline_id}


@router.get("/{pipeline_id}/runs")
async def get_pipeline_runs(pipeline_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PipelineRun)
        .where(PipelineRun.pipeline_id == pipeline_id)
        .order_by(PipelineRun.started_at.desc())
        .limit(50)
    )
    rows = result.scalars().all()
    return {"items": [_serialize_run(r) for r in rows]}


async def _get_or_404(pipeline_id: str, db: AsyncSession) -> Pipeline:
    result = await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return row


def _serialize(p: Pipeline) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "status": p.status.value if p.status else None,
        "source_connector_id": p.source_connector_id,
        "target_connector_id": p.target_connector_id,
        "entity_name": p.entity_name,
        "direction": p.direction.value if p.direction else None,
        "poll_interval_seconds": p.poll_interval_seconds,
        "use_cdc": p.use_cdc,
        "last_sync_at": p.last_sync_at.isoformat() if p.last_sync_at else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _serialize_run(r: PipelineRun) -> dict:
    return {
        "id": r.id,
        "pipeline_id": r.pipeline_id,
        "trigger": r.trigger,
        "status": r.status,
        "records_processed": r.records_processed,
        "records_succeeded": r.records_succeeded,
        "records_failed": r.records_failed,
        "records_skipped": r.records_skipped,
        "error_message": r.error_message,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "duration_ms": r.duration_ms,
    }
