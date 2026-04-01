"""
SchemaRegistryService: store, version, and diff ERP entity schemas.
When a schema changes, a SchemaDiff is created and the agent is notified.
"""
import hashlib
import json
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import SchemaDiff, SchemaVersion
from .differ import SchemaDiffer


class SchemaRegistryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.differ = SchemaDiffer()

    async def ingest_schema(
        self,
        connector_id: str,
        entity_schema,  # EntitySchema from connector
    ) -> tuple[SchemaVersion, Optional[SchemaDiff]]:
        """
        Store a newly fetched schema snapshot.
        Returns (schema_version, diff_or_None).
        diff is None when schema is unchanged.
        """
        new_hash = self._compute_hash(entity_schema)

        stmt = select(SchemaVersion).where(
            SchemaVersion.connector_id == connector_id,
            SchemaVersion.entity_name == entity_schema.entity_name,
            SchemaVersion.is_current == True,
        )
        result = await self.db.execute(stmt)
        current: Optional[SchemaVersion] = result.scalar_one_or_none()

        if current and current.version_hash == new_hash:
            return current, None  # no change

        version_number = (current.version_number + 1) if current else 1

        diff: Optional[SchemaDiff] = None
        if current:
            diff_data = self.differ.diff(current.schema_json, entity_schema.model_dump())
            diff = SchemaDiff(
                id=str(uuid.uuid4()),
                from_version_id=current.id,
                diff_json=diff_data,
                agent_triggered=bool(
                    diff_data.get("added") or diff_data.get("removed") or diff_data.get("changed")
                ),
            )
            await self.db.execute(
                update(SchemaVersion)
                .where(SchemaVersion.id == current.id)
                .values(is_current=False)
            )

        new_version = SchemaVersion(
            id=str(uuid.uuid4()),
            connector_id=connector_id,
            entity_name=entity_schema.entity_name,
            version_number=version_number,
            version_hash=new_hash,
            schema_json=entity_schema.model_dump(),
            is_current=True,
            drift_detected=diff is not None,
            drift_summary=diff.diff_json if diff else None,
        )
        self.db.add(new_version)
        if diff:
            diff.to_version_id = new_version.id
            self.db.add(diff)
        await self.db.commit()
        await self.db.refresh(new_version)
        return new_version, diff

    async def get_current_schema(
        self, connector_id: str, entity_name: str
    ) -> Optional[SchemaVersion]:
        stmt = select(SchemaVersion).where(
            SchemaVersion.connector_id == connector_id,
            SchemaVersion.entity_name == entity_name,
            SchemaVersion.is_current == True,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_entities(self, connector_id: str) -> list[str]:
        stmt = select(SchemaVersion.entity_name).where(
            SchemaVersion.connector_id == connector_id,
            SchemaVersion.is_current == True,
        )
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]

    async def list_diffs(
        self, connector_id: str, entity_name: str
    ) -> list[SchemaDiff]:
        subq = select(SchemaVersion.id).where(
            SchemaVersion.connector_id == connector_id,
            SchemaVersion.entity_name == entity_name,
        )
        stmt = select(SchemaDiff).where(
            SchemaDiff.to_version_id.in_(subq)
        ).order_by(SchemaDiff.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    def _compute_hash(self, schema) -> str:
        canonical = json.dumps(
            sorted([f.model_dump() for f in schema.fields], key=lambda f: f["name"]),
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()
