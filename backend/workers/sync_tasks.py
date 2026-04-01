"""Celery tasks for pipeline sync operations."""
import asyncio
import logging

from .celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from a synchronous Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    name="backend.workers.sync_tasks.run_pipeline_sync",
    max_retries=3,
    default_retry_delay=60,
)
def run_pipeline_sync(self, pipeline_id: str, direction: str = "both"):
    """Run a full sync cycle for a pipeline.

    direction: "forward" | "reverse" | "both"
    """
    logger.info("Starting sync for pipeline %s (direction=%s)", pipeline_id, direction)
    try:
        _run_async(_async_run_pipeline_sync(pipeline_id, direction))
    except Exception as exc:
        logger.error("Sync failed for pipeline %s: %s", pipeline_id, exc)
        raise self.retry(exc=exc)


async def _async_run_pipeline_sync(pipeline_id: str, direction: str):
    from ..core.database import AsyncSessionLocal
    from ..db.models import Pipeline, ConnectorRecord
    from ..connectors.registry import ConnectorRegistry
    from ..pipeline.runner import PipelineRunner
    from ..transformation.sandbox import TransformationEngine
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        # Load pipeline
        result = await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))
        pipeline = result.scalar_one_or_none()
        if not pipeline:
            logger.warning("Pipeline %s not found — skipping sync.", pipeline_id)
            return
        if pipeline.status != "active":
            logger.info("Pipeline %s is not active — skipping.", pipeline_id)
            return

        # Load connectors
        registry = ConnectorRegistry()
        registry.discover()

        source_result = await db.execute(
            select(ConnectorRecord).where(ConnectorRecord.id == pipeline.source_connector_id)
        )
        source_record = source_result.scalar_one_or_none()
        target_result = await db.execute(
            select(ConnectorRecord).where(ConnectorRecord.id == pipeline.target_connector_id)
        )
        target_record = target_result.scalar_one_or_none()

        if not source_record or not target_record:
            logger.error("Connector records missing for pipeline %s", pipeline_id)
            return

        source = registry.create(
            source_record.connector_type,
            {"id": str(source_record.id), **source_record.config, **source_record.credentials},
        )
        target = registry.create(
            target_record.connector_type,
            {"id": str(target_record.id), **target_record.config, **target_record.credentials},
        )

        runner = PipelineRunner(db=db, source=source, target=target)

        if direction in ("forward", "both"):
            await runner.run(pipeline, direction="forward")
        if direction in ("reverse", "both"):
            await runner.run(pipeline, direction="reverse")


@celery_app.task(
    name="backend.workers.sync_tasks.run_schema_discovery",
    max_retries=2,
    default_retry_delay=30,
)
def run_schema_discovery(connector_id: str):
    """Discover and update schemas for a connector, then index into NAM."""
    logger.info("Running schema discovery for connector %s", connector_id)
    _run_async(_async_schema_discovery(connector_id))


async def _async_schema_discovery(connector_id: str):
    from ..core.database import AsyncSessionLocal
    from ..db.models import ConnectorRecord
    from ..connectors.registry import ConnectorRegistry
    from ..schema_registry.service import SchemaRegistryService
    from ..llm.nam_client import NAMClient
    from ..llm.schema_indexer import SchemaIndexer
    from ..core.config import settings
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ConnectorRecord).where(ConnectorRecord.id == connector_id)
        )
        record = result.scalar_one_or_none()
        if not record:
            logger.warning("Connector %s not found", connector_id)
            return

        registry = ConnectorRegistry()
        registry.discover()
        connector = registry.create(
            record.connector_type,
            {"id": str(record.id), **record.config, **record.credentials},
        )

        await connector.connect()
        try:
            entities = await connector.list_entities()
            svc = SchemaRegistryService(db)
            nam = NAMClient(
                query_url=settings.nam_query_url,
                encoder_url=settings.nam_encoder_url,
            )
            indexer = SchemaIndexer(nam)

            for entity_name in entities:
                schema = await connector.read_schema(entity_name)
                version, diff = await svc.ingest_schema(
                    connector_id=connector_id,
                    entity_name=entity_name,
                    schema_json=schema.fields,
                )
                await indexer.index_schema_version(version)
                if diff:
                    await indexer.index_schema_diff(diff, connector_id, entity_name)
                    logger.info("Schema drift indexed for %s/%s", connector_id, entity_name)

            logger.info("Schema discovery complete for connector %s (%d entities)", connector_id, len(entities))
        finally:
            await connector.disconnect()
