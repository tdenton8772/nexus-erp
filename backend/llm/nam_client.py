"""
NAM HTTP client.

NAM (Neural Addressed Memory) is the semantic storage and retrieval layer.
It indexes ERP schemas, field descriptions, sync history, and agent context
as semantically addressed documents, enabling grounded retrieval without
hallucination.

Ports (from nam-0.0.1 FastAPI server):
  NAM query server : NAM_QUERY_URL  (default http://localhost:8000 on NAM's own server)
  NAM encoder      : NAM_ENCODER_URL (default http://localhost:8010)
"""
import logging
from typing import Any, Optional

import httpx

from ..core.config import settings

logger = logging.getLogger(__name__)


class NAMClient:
    """
    Wraps NAM's HTTP query and ingest endpoints.

    Used by:
      - NNLMClient (for retrieval during agent runs)
      - SchemaIndexer (to ingest schema definitions into NAM on discovery)
      - AgentContextIndexer (to ingest pipeline history + sync events)
    """

    def __init__(self) -> None:
        self._query_url = settings.nam_query_url
        self._encoder_url = settings.nam_encoder_url
        self._http = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._http.aclose()

    # ── Query ──────────────────────────────────────────────────────────────────

    async def query(
        self,
        query: str,
        limit: int = 20,
        mode: str = "AFFORDANCE",
        namespace: str = "nexus",
    ) -> dict[str, Any]:
        """
        Execute a semantic query against NAM.
        Returns NAM QueryResponse dict:
          {ok, mode, affordance, results: [{text, record_id, relevance_score}], errors}
        """
        payload = {
            "query": query,
            "limit": limit,
            "namespace": namespace,
            "hints": {"mode": mode},
        }
        try:
            resp = await self._http.post(f"{self._query_url}/v1/query", json=payload)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.error("NAM query failed: %s", exc)
            return {"ok": False, "results": [], "errors": [str(exc)]}

    async def bulk_query(self, queries: list[str], limit: int = 10) -> list[dict]:
        """Batch multiple queries in a single NAM call."""
        payload = [{"query": q, "limit": limit} for q in queries]
        try:
            resp = await self._http.post(f"{self._query_url}/v1/query/bulk", json=payload)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.error("NAM bulk query failed: %s", exc)
            return []

    # ── Ingest ─────────────────────────────────────────────────────────────────

    async def ingest_document(
        self,
        key: str,
        content: str,
        bucket: str = "nexus_erp",
        metadata: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        Ingest a document into NAM's semantic index.
        Used to index ERP schemas, field descriptions, and agent history.
        """
        payload = {
            "records": [
                {
                    "key": key,
                    "doc_id": key,
                    "bucket": bucket,
                    "content": content,
                    "metadata": metadata or {},
                }
            ]
        }
        try:
            resp = await self._http.post(f"{self._query_url}/v1/ingest", json=payload)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.error("NAM ingest failed for key=%s: %s", key, exc)
            return {"ok": False, "errors": [str(exc)]}

    async def ingest_schema(self, connector_id: str, entity_name: str, schema_json: dict) -> None:
        """
        Index an ERP entity schema into NAM so the agent can retrieve
        field definitions semantically (e.g. 'what field holds the invoice total?').
        """
        # Flatten schema to human-readable text for NAM encoding
        fields_text = "\n".join(
            f"  - {f['name']} ({f['data_type']}): {f.get('description', 'no description')}"
            for f in schema_json.get("fields", [])
        )
        content = (
            f"ERP Schema: {entity_name} on connector {connector_id}\n"
            f"System: {schema_json.get('system_name', 'unknown')}\n"
            f"Fields:\n{fields_text}"
        )
        key = f"schema:{connector_id}:{entity_name}"
        await self.ingest_document(key=key, content=content, metadata={
            "connector_id": connector_id,
            "entity_name": entity_name,
            "type": "schema",
        })

    async def ingest_mapping(self, pipeline_id: str, mapping_summary: str) -> None:
        """Index an approved field mapping into NAM for future healing context."""
        key = f"mapping:{pipeline_id}"
        await self.ingest_document(key=key, content=mapping_summary, metadata={
            "pipeline_id": pipeline_id,
            "type": "mapping",
        })

    async def ingest_sync_event(self, event_summary: str, pipeline_id: str, record_id: str) -> None:
        """Index a sync event error or anomaly for the self-healing agent."""
        key = f"sync_event:{pipeline_id}:{record_id}"
        await self.ingest_document(key=key, content=event_summary, metadata={
            "pipeline_id": pipeline_id,
            "record_id": record_id,
            "type": "sync_event",
        })

    # ── Health ─────────────────────────────────────────────────────────────────

    async def health(self) -> bool:
        try:
            resp = await self._http.get(f"{self._query_url}/health", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False
