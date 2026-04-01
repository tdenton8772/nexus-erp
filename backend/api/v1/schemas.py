"""Schema registry endpoints."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...db.models import ConnectorRecord, SchemaVersion, SchemaDiff
from ...schema_registry.service import SchemaRegistryService
from ...connectors.registry import ConnectorRegistry
from ...connectors.base import ConnectorConfig
from ...core.security import decrypt_credentials
from ...llm.nam_client import NAMClient
from ...llm.schema_indexer import SchemaIndexer

router = APIRouter()


@router.get("/{connector_id}")
async def list_schemas(connector_id: str, db: AsyncSession = Depends(get_db)):
    svc = SchemaRegistryService(db)
    entities = await svc.list_entities(connector_id)
    return {"connector_id": connector_id, "entities": entities}


@router.get("/{connector_id}/{entity_name}")
async def get_schema(connector_id: str, entity_name: str, db: AsyncSession = Depends(get_db)):
    svc = SchemaRegistryService(db)
    schema = await svc.get_current_schema(connector_id, entity_name)
    if not schema:
        raise HTTPException(status_code=404, detail="Schema not found")
    return {
        "id": schema.id,
        "connector_id": schema.connector_id,
        "entity_name": schema.entity_name,
        "version_number": schema.version_number,
        "version_hash": schema.version_hash,
        "schema_json": schema.schema_json,
        "drift_detected": schema.drift_detected,
        "captured_at": schema.captured_at.isoformat() if schema.captured_at else None,
    }


@router.post("/{connector_id}/discover", status_code=202)
async def trigger_schema_discovery(
    connector_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ConnectorRecord).where(ConnectorRecord.id == connector_id))
    connector_rec = result.scalar_one_or_none()
    if not connector_rec:
        raise HTTPException(status_code=404, detail="Connector not found")

    background_tasks.add_task(_run_discovery, connector_id)
    return {"status": "discovery_started", "connector_id": connector_id}


async def _run_discovery(connector_id: str) -> None:
    from ...core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ConnectorRecord).where(ConnectorRecord.id == connector_id))
        connector_rec = result.scalar_one_or_none()
        if not connector_rec:
            return

        creds = decrypt_credentials(connector_rec.credentials_encrypted) if connector_rec.credentials_encrypted else {}
        config = ConnectorConfig(
            connector_id=connector_rec.id,
            system_name=connector_rec.system_name,
            credentials=creds,
            base_url=connector_rec.base_url or "",
        )

        try:
            connector = ConnectorRegistry.create(config)
        except KeyError:
            return

        svc = SchemaRegistryService(db)
        nam = NAMClient()
        indexer = SchemaIndexer(nam)

        entities = await connector.list_entities()
        for entity_name in entities:
            try:
                schema = await connector.read_schema(entity_name)
                version, diff = await svc.ingest_schema(connector_id, schema)
                await indexer.index_schema_version(version)
                if diff and diff.agent_triggered:
                    await indexer.index_schema_diff(diff, connector_id, entity_name)
            except Exception:
                pass

        await nam.close()


@router.get("/{connector_id}/{entity_name}/diffs")
async def list_diffs(connector_id: str, entity_name: str, db: AsyncSession = Depends(get_db)):
    svc = SchemaRegistryService(db)
    diffs = await svc.list_diffs(connector_id, entity_name)
    return {
        "items": [
            {
                "id": d.id,
                "from_version_id": d.from_version_id,
                "to_version_id": d.to_version_id,
                "diff_json": d.diff_json,
                "agent_triggered": d.agent_triggered,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in diffs
        ]
    }
