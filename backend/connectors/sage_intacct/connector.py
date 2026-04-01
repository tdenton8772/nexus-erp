"""Sage Intacct ERP connector."""
from datetime import datetime
from typing import Any, AsyncIterator, Optional
from ..base import ERPConnector, ConnectorConfig, ConnectorCapability, ConnectorMeta, EntitySchema, SyncRecord
from .client import IntacctClient
from .schema_adapter import IntacctSchemaAdapter


class SageIntacctConnector(ERPConnector):
    class Meta(ConnectorMeta):
        system_name = "sage_intacct"
        display_name = "Sage Intacct"
        version = "1.0.0"
        capabilities = [ConnectorCapability.POLLING, ConnectorCapability.BIDIRECTIONAL]
        supported_entities = ["APBILL", "VENDOR", "CUSTOMER", "GLACCOUNT", "GLENTRY", "INVOICE", "SOTRANSACTION"]

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        c = config.credentials
        self._client = IntacctClient(
            company_id=c["company_id"], user_id=c["user_id"], password=c["password"],
            sender_id=c["sender_id"], sender_password=c["sender_password"], base_url=config.base_url,
        )
        self._adapter = IntacctSchemaAdapter()

    async def connect(self) -> None:
        await self._client.authenticate()

    async def disconnect(self) -> None:
        await self._client.close_session()

    async def list_entities(self) -> list[str]:
        return self.Meta.supported_entities

    async def read_schema(self, entity_name: str) -> EntitySchema:
        await self.connect()
        raw = await self._client.get_object_definition(entity_name)
        await self.disconnect()
        return self._adapter.adapt(entity_name, raw)

    async def fetch_records(self, entity_name, since=None, page_size=500, cursor=None):
        await self.connect()
        raw_records, next_cursor = await self._client.query(
            object_name=entity_name, modified_since=since, page_size=page_size,
            offset=int(cursor) if cursor else 0,
        )
        await self.disconnect()
        records = [
            SyncRecord(
                record_id=r.get("RECORDNO", str(i)), entity_name=entity_name,
                source_system=self.Meta.system_name, payload=r,
                updated_at=datetime.fromisoformat(r["WHENMODIFIED"].replace("/", "-")) if r.get("WHENMODIFIED") else datetime.utcnow(),
                operation="update" if r.get("WHENMODIFIED") else "create",
            )
            for i, r in enumerate(raw_records)
        ]
        return records, next_cursor

    async def push_records(self, entity_name, records):
        await self.connect()
        results = []
        for record in records:
            result = await self._client.upsert(entity_name, record.payload)
            results.append({"record_id": record.record_id, "status": "success" if result.get("status") == "success" else "error", "erp_id": result.get("key"), "error": result.get("errormessage")})
        await self.disconnect()
        return results

    async def subscribe_to_changes(self, entity_name: str) -> AsyncIterator[SyncRecord]:
        raise NotImplementedError("Sage Intacct does not support streaming CDC. Use polling.")
