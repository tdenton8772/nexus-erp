"""
PipelineRunner: executes one full sync cycle for a pipeline.
Fetches from source, transforms, resolves conflicts, pushes to target,
and writes SyncEvents to the DB.
"""
import hashlib
import json
import logging
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from ..connectors.base import SyncRecord
from ..connectors.registry import ConnectorRegistry
from ..db.models import (
    ExternalIdMap, Pipeline, PipelineRun, SyncEvent, SyncEventStatus,
    SyncDirection, CompiledTransformation,
)
from ..transformation.sandbox import TransformationEngine
from .conflict import ConflictResolver

logger = logging.getLogger(__name__)


class PipelineRunner:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.conflict_resolver = ConflictResolver()

    async def run(self, pipeline: Pipeline, trigger: str = "manual") -> PipelineRun:
        run = PipelineRun(
            id=str(uuid.uuid4()),
            pipeline_id=pipeline.id,
            trigger=trigger,
            status="running",
            started_at=datetime.utcnow(),
        )
        self.db.add(run)
        await self.db.commit()

        try:
            await self._execute(pipeline, run)
            run.status = "completed"
        except Exception as exc:
            logger.error("Pipeline %s run failed: %s", pipeline.id, exc, exc_info=True)
            run.status = "failed"
            run.error_message = str(exc)
        finally:
            run.completed_at = datetime.utcnow()
            if run.started_at:
                run.duration_ms = int((run.completed_at - run.started_at).total_seconds() * 1000)
            await self.db.commit()

        return run

    async def _execute(self, pipeline: Pipeline, run: PipelineRun) -> None:
        # Load transformation
        stmt = select(CompiledTransformation).where(CompiledTransformation.pipeline_id == pipeline.id)
        result = await self.db.execute(stmt)
        compiled = result.scalar_one_or_none()

        engine: TransformationEngine | None = None
        if compiled and compiled.validation_passed:
            engine = TransformationEngine(compiled.forward_code, compiled.reverse_code)

        # Load source connector
        from ..core.security import decrypt_credentials
        src_stmt = select(Pipeline).where(Pipeline.id == pipeline.id)
        # Connectors loaded from DB records
        from ..db.models import ConnectorRecord
        src_conn_stmt = select(ConnectorRecord).where(ConnectorRecord.id == pipeline.source_connector_id)
        tgt_conn_stmt = select(ConnectorRecord).where(ConnectorRecord.id == pipeline.target_connector_id)

        src_conn_rec = (await self.db.execute(src_conn_stmt)).scalar_one()
        tgt_conn_rec = (await self.db.execute(tgt_conn_stmt)).scalar_one()

        from ..connectors.base import ConnectorConfig
        src_creds = decrypt_credentials(src_conn_rec.credentials_encrypted) if src_conn_rec.credentials_encrypted else {}
        tgt_creds = decrypt_credentials(tgt_conn_rec.credentials_encrypted) if tgt_conn_rec.credentials_encrypted else {}

        src_config = ConnectorConfig(connector_id=src_conn_rec.id, system_name=src_conn_rec.system_name, credentials=src_creds, base_url=src_conn_rec.base_url or "")
        tgt_config = ConnectorConfig(connector_id=tgt_conn_rec.id, system_name=tgt_conn_rec.system_name, credentials=tgt_creds, base_url=tgt_conn_rec.base_url or "")

        src = ConnectorRegistry.create(src_config)
        tgt = ConnectorRegistry.create(tgt_config)

        # Fetch source records (delta since last sync)
        records, _ = await src.fetch_records(
            entity_name=pipeline.entity_name,
            since=pipeline.last_sync_at,
            page_size=500,
        )

        run.records_processed = len(records)
        succeeded = failed = skipped = 0

        for record in records:
            event = SyncEvent(
                id=str(uuid.uuid4()),
                pipeline_id=pipeline.id,
                record_id=record.record_id,
                entity_name=record.entity_name,
                source_system=src_conn_rec.system_name,
                target_system=tgt_conn_rec.system_name,
                direction=SyncDirection.SOURCE_TO_TARGET,
                operation=record.operation,
                status=SyncEventStatus.IN_PROGRESS,
                source_payload_hash=hashlib.sha256(json.dumps(record.payload, sort_keys=True, default=str).encode()).hexdigest(),
            )
            self.db.add(event)

            try:
                # Check loop prevention
                id_map_stmt = select(ExternalIdMap).where(
                    ExternalIdMap.pipeline_id == pipeline.id,
                    ExternalIdMap.source_system == src_conn_rec.system_name,
                    ExternalIdMap.source_record_id == record.record_id,
                )
                id_map = (await self.db.execute(id_map_stmt)).scalar_one_or_none()

                if id_map and id_map.last_payload_hash == event.source_payload_hash:
                    event.status = SyncEventStatus.SKIPPED
                    event.conflict_resolution = "loop_prevention_unchanged"
                    skipped += 1
                    continue

                # Conflict resolution
                existing_updated_at = id_map.last_synced_at if id_map else None
                should_apply, reason = await self.conflict_resolver.resolve(record, existing_updated_at, pipeline.id)

                if not should_apply:
                    event.status = SyncEventStatus.SKIPPED
                    event.conflict_resolution = reason
                    skipped += 1
                    continue

                # Transform
                payload = record.payload
                if engine:
                    payload = engine.transform_forward(payload, {"pipeline_id": pipeline.id})

                transformed = SyncRecord(
                    record_id=record.record_id,
                    entity_name=record.entity_name,
                    source_system=record.source_system,
                    payload=payload,
                    updated_at=record.updated_at,
                    operation=record.operation,
                )

                results = await tgt.push_records(pipeline.entity_name, [transformed])
                result_item = results[0] if results else {}

                if result_item.get("status") == "success":
                    event.status = SyncEventStatus.SUCCESS
                    event.target_erp_id = result_item.get("erp_id")
                    event.conflict_resolution = reason

                    # Update external ID map
                    if id_map:
                        id_map.last_synced_at = record.updated_at
                        id_map.last_payload_hash = event.source_payload_hash
                        if result_item.get("erp_id"):
                            id_map.target_record_id = result_item["erp_id"]
                    else:
                        self.db.add(ExternalIdMap(
                            id=str(uuid.uuid4()),
                            pipeline_id=pipeline.id,
                            source_system=src_conn_rec.system_name,
                            source_record_id=record.record_id,
                            target_system=tgt_conn_rec.system_name,
                            target_record_id=result_item.get("erp_id", ""),
                            last_synced_at=record.updated_at,
                            last_payload_hash=event.source_payload_hash,
                        ))
                    succeeded += 1
                else:
                    event.status = SyncEventStatus.FAILED
                    event.error_message = result_item.get("error")
                    failed += 1

            except Exception as exc:
                event.status = SyncEventStatus.FAILED
                event.error_message = str(exc)
                failed += 1
                logger.error("Record sync failed: pipeline=%s record=%s: %s", pipeline.id, record.record_id, exc)

            event.completed_at = datetime.utcnow()

        # Update pipeline last_sync_at
        await self.db.execute(
            update(Pipeline)
            .where(Pipeline.id == pipeline.id)
            .values(last_sync_at=datetime.utcnow())
        )

        run.records_succeeded = succeeded
        run.records_failed = failed
        run.records_skipped = skipped
        await self.db.commit()
