"""
SchemaIndexer: bridges the schema registry and NAM.

Whenever a schema is discovered or updated, SchemaIndexer ingests it into NAM
so the NNLM agent can retrieve field definitions semantically when proposing
mappings or diagnosing drift.
"""
import logging

from .nam_client import NAMClient

logger = logging.getLogger(__name__)


class SchemaIndexer:
    def __init__(self, nam: NAMClient) -> None:
        self.nam = nam

    async def index_schema_version(self, schema_version) -> None:
        """Index a SchemaVersion DB record into NAM."""
        await self.nam.ingest_schema(
            connector_id=schema_version.connector_id,
            entity_name=schema_version.entity_name,
            schema_json=schema_version.schema_json,
        )
        logger.info(
            "Indexed schema into NAM: connector=%s entity=%s v%s",
            schema_version.connector_id,
            schema_version.entity_name,
            schema_version.version_number,
        )

    async def index_schema_diff(self, diff, connector_id: str, entity_name: str) -> None:
        """Index a schema drift event into NAM for healing context."""
        added = diff.diff_json.get("added", [])
        removed = diff.diff_json.get("removed", [])
        changed = diff.diff_json.get("changed", [])

        parts = [f"Schema drift detected on {entity_name} (connector {connector_id})."]
        if added:
            parts.append(f"Added fields: {', '.join(f['name'] for f in added)}")
        if removed:
            parts.append(f"Removed fields: {', '.join(f['name'] for f in removed)}")
        if changed:
            parts.append(
                f"Changed fields: "
                + ", ".join(
                    f"{c['name']} ({c['old']['type']} → {c['new']['type']})"
                    for c in changed
                )
            )

        content = " ".join(parts)
        key = f"drift:{diff.id}"
        await self.nam.ingest_document(
            key=key,
            content=content,
            metadata={
                "connector_id": connector_id,
                "entity_name": entity_name,
                "diff_id": diff.id,
                "type": "schema_drift",
            },
        )

    async def index_approved_mapping(self, pipeline_id: str, field_mappings: list) -> None:
        """Index an approved mapping into NAM so future proposals can reference it."""
        lines = [f"Approved field mappings for pipeline {pipeline_id}:"]
        for m in field_mappings:
            src = m.get("source_field") or "(computed)"
            tgt = m.get("target_field") or "(none)"
            transform = m.get("transform_name", "passthrough")
            lines.append(f"  {src} --[{transform}]--> {tgt}")

        content = "\n".join(lines)
        await self.nam.ingest_mapping(
            pipeline_id=pipeline_id,
            mapping_summary=content,
        )

    async def index_failed_sync(
        self, pipeline_id: str, record_id: str, error: str, entity_name: str
    ) -> None:
        """Index a sync failure into NAM so the healing agent has context."""
        content = (
            f"Sync failure on pipeline {pipeline_id}, entity {entity_name}, "
            f"record {record_id}. Error: {error}"
        )
        await self.nam.ingest_sync_event(
            event_summary=content,
            pipeline_id=pipeline_id,
            record_id=record_id,
        )
