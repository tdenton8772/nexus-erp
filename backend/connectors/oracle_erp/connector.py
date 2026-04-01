"""Oracle ERP Cloud connector via REST API."""
from datetime import datetime
from typing import AsyncIterator
import httpx, hashlib, json, base64
from ..base import ERPConnector, ConnectorConfig, ConnectorCapability, ConnectorMeta, EntitySchema, SyncRecord, SchemaField


class OracleERPConnector(ERPConnector):
    class Meta(ConnectorMeta):
        system_name = "oracle_erp"
        display_name = "Oracle ERP Cloud"
        version = "1.0.0"
        capabilities = [ConnectorCapability.POLLING, ConnectorCapability.BIDIRECTIONAL]
        supported_entities = ["invoices", "suppliers", "customers", "journals", "accounts", "purchaseOrders"]

    async def connect(self) -> None:
        c = self.config.credentials
        token = base64.b64encode(f"{c['username']}:{c['password']}".encode()).decode()
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            headers={"Authorization": f"Basic {token}", "Content-Type": "application/json", "Accept": "application/json"},
            timeout=30.0,
        )

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()

    async def list_entities(self) -> list[str]:
        return self.Meta.supported_entities

    async def read_schema(self, entity_name: str) -> EntitySchema:
        await self.connect()
        resp = await self._client.get(f"/fscmRestApi/resources/11.13.18.05/{entity_name}?limit=1")
        items = resp.json().get("items", [{}]) if resp.is_success else [{}]
        sample = items[0] if items else {}
        fields = [SchemaField(name=k, canonical_name=k.lower(), data_type="string") for k in sample]
        version_hash = hashlib.sha256(json.dumps(sorted(f.name for f in fields)).encode()).hexdigest()
        await self.disconnect()
        return EntitySchema(entity_name=entity_name, system_name=self.Meta.system_name, version_hash=version_hash, fields=fields, fetched_at=datetime.utcnow())

    async def fetch_records(self, entity_name, since=None, page_size=500, cursor=None):
        await self.connect()
        url = f"/fscmRestApi/resources/11.13.18.05/{entity_name}?limit={page_size}"
        if cursor:
            url += f"&offset={cursor}"
        resp = await self._client.get(url)
        data = resp.json() if resp.is_success else {"items": []}
        records = [
            SyncRecord(record_id=str(r.get("InvoiceId", r.get("SupplierId", i))), entity_name=entity_name,
                       source_system=self.Meta.system_name, payload=r, updated_at=datetime.utcnow(), operation="update")
            for i, r in enumerate(data.get("items", []))
        ]
        has_more = data.get("hasMore", False)
        offset = int(cursor or 0) + page_size
        next_cursor = str(offset) if has_more else None
        await self.disconnect()
        return records, next_cursor

    async def push_records(self, entity_name, records):
        await self.connect()
        results = []
        for record in records:
            resp = await self._client.post(f"/fscmRestApi/resources/11.13.18.05/{entity_name}", json=record.payload)
            results.append({"record_id": record.record_id, "status": "success" if resp.is_success else "error", "erp_id": resp.json().get("InvoiceId") if resp.is_success else None, "error": None if resp.is_success else resp.text})
        await self.disconnect()
        return results

    async def subscribe_to_changes(self, entity_name):
        raise NotImplementedError("Oracle ERP Cloud CDC not supported. Use polling.")
