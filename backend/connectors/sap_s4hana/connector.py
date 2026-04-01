"""SAP S/4HANA connector via OData v4 REST API."""
from datetime import datetime
from typing import AsyncIterator
import httpx, hashlib, json, base64
from ..base import ERPConnector, ConnectorConfig, ConnectorCapability, ConnectorMeta, EntitySchema, SyncRecord, SchemaField


class SAPS4HanaConnector(ERPConnector):
    class Meta(ConnectorMeta):
        system_name = "sap_s4hana"
        display_name = "SAP S/4HANA"
        version = "1.0.0"
        capabilities = [ConnectorCapability.POLLING, ConnectorCapability.BIDIRECTIONAL]
        supported_entities = ["A_SupplierInvoice", "A_BusinessPartner", "A_CustomerMaterial", "A_GLAccountInCompanyCode", "A_JournalEntry"]

    async def connect(self) -> None:
        c = self.config.credentials
        token = base64.b64encode(f"{c['username']}:{c['password']}".encode()).decode()
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            headers={"Authorization": f"Basic {token}", "Accept": "application/json", "Content-Type": "application/json"},
            timeout=30.0,
        )
        # SAP requires CSRF token for write operations
        resp = await self._client.get("/sap/opu/odata/sap/API_SUPPLIER_INVOICE_SRV/", headers={"X-CSRF-Token": "Fetch"})
        self._csrf_token = resp.headers.get("x-csrf-token", "")

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()

    async def list_entities(self) -> list[str]:
        return self.Meta.supported_entities

    async def read_schema(self, entity_name: str) -> EntitySchema:
        await self.connect()
        resp = await self._client.get(f"/sap/opu/odata4/sap/api_{entity_name.lower()}/srvd_a2x/sap/{entity_name}/0001/{entity_name}?$top=1&$format=json")
        sample = resp.json().get("value", [{}]) if resp.is_success else [{}]
        sample_record = sample[0] if sample else {}
        fields = [SchemaField(name=k, canonical_name=k.lower(), data_type="string") for k in sample_record]
        version_hash = hashlib.sha256(json.dumps(sorted(f.name for f in fields)).encode()).hexdigest()
        await self.disconnect()
        return EntitySchema(entity_name=entity_name, system_name=self.Meta.system_name, version_hash=version_hash, fields=fields, fetched_at=datetime.utcnow())

    async def fetch_records(self, entity_name, since=None, page_size=500, cursor=None):
        await self.connect()
        url = f"/sap/opu/odata4/sap/api_{entity_name.lower()}/srvd_a2x/sap/{entity_name}/0001/{entity_name}?$top={page_size}&$format=json"
        if since:
            url += f"&$filter=LastChangeDateTime gt datetime'{since.isoformat()}'"
        resp = await self._client.get(url)
        data = resp.json() if resp.is_success else {"value": []}
        records = [
            SyncRecord(record_id=str(r.get(f"{entity_name}UUID", i)), entity_name=entity_name,
                       source_system=self.Meta.system_name, payload=r, updated_at=datetime.utcnow(), operation="update")
            for i, r in enumerate(data.get("value", []))
        ]
        await self.disconnect()
        return records, data.get("@odata.nextLink")

    async def push_records(self, entity_name, records):
        await self.connect()
        results = []
        for record in records:
            resp = await self._client.post(
                f"/sap/opu/odata4/sap/api_{entity_name.lower()}/srvd_a2x/sap/{entity_name}/0001/{entity_name}",
                json=record.payload, headers={"X-CSRF-Token": self._csrf_token}
            )
            results.append({"record_id": record.record_id, "status": "success" if resp.is_success else "error", "erp_id": None, "error": None if resp.is_success else resp.text})
        await self.disconnect()
        return results

    async def subscribe_to_changes(self, entity_name):
        raise NotImplementedError("SAP S/4HANA CDC not supported. Use polling.")
